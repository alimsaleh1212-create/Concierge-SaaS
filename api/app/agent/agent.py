import uuid
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import chat_completion
from app.agent.tools.rag_search import RagSearchTool
from app.agent.tools.capture_lead import CaptureLeadTool
from app.agent.tools.escalate import EscalateTool

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5
MAX_OUTPUT_TOKENS = 2000
_FALLBACK_TEXT = (
    "I'm sorry, I wasn't able to fully resolve your request. "
    "I've connected you with our team and someone will be in touch shortly."
)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_system_template: str | None = None


def _load_system_template() -> str:
    global _system_template
    if _system_template is None:
        _system_template = (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
    return _system_template


@dataclass
class TenantContext:
    tenant_id: uuid.UUID
    widget_id: uuid.UUID
    conversation_id: uuid.UUID
    tenant_name: str
    persona: str
    allowed_topics: str
    visitor_ip: str | None = None


@dataclass
class AgentResult:
    response: str
    tool_used: str | None = None
    escalated: bool = False
    lead_captured: bool = False


class ToolCallingAgent:
    def __init__(self, tenant_ctx: TenantContext, session: AsyncSession) -> None:
        self.tenant_ctx = tenant_ctx
        self.session = session
        self._tools = {
            "rag_search": RagSearchTool(
                tenant_id=tenant_ctx.tenant_id,
                session=session,
                conversation_id=tenant_ctx.conversation_id,
            ),
            "capture_lead": CaptureLeadTool(
                tenant_ctx.tenant_id,
                tenant_ctx.conversation_id,
                session,
                visitor_ip=tenant_ctx.visitor_ip,
            ),
            "escalate": EscalateTool(tenant_ctx.tenant_id, tenant_ctx.conversation_id, session),
        }

    @property
    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [t.schema for t in self._tools.values()]

    def _build_system(self) -> str:
        ctx = self.tenant_ctx
        return (
            _load_system_template()
            .replace("{{tenant_name}}", ctx.tenant_name)
            .replace("{{persona}}", ctx.persona)
            .replace("{{allowed_topics}}", ctx.allowed_topics)
        )

    async def _execute_tool(self, name: str, inputs: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Unknown tool: {name}"
        return await tool(**inputs)

    async def run(self, messages: list[dict[str, Any]]) -> AgentResult:
        system = self._build_system()
        iteration = 0
        total_output_tokens = 0
        last_tool: str | None = None
        lead_captured = False
        escalated = False

        while iteration < MAX_ITERATIONS:
            response = await chat_completion(
                messages=messages,
                system=system,
                tools=self._tool_schemas,
                max_tokens=MAX_OUTPUT_TOKENS,
                tenant_id=self.tenant_ctx.tenant_id,
                conversation_id=self.tenant_ctx.conversation_id,
            )
            turn_tokens = response.usage.output_tokens
            total_output_tokens += turn_tokens
            logger.info(
                "agent.turn iteration=%d stop_reason=%s turn_tokens=%d total_tokens=%d",
                iteration,
                response.stop_reason,
                turn_tokens,
                total_output_tokens,
            )

            if response.stop_reason == "end_turn":
                text_blocks = [b for b in response.content if b.type == "text"]
                text = text_blocks[0].text if text_blocks else ""
                return AgentResult(
                    response=text,
                    tool_used=last_tool,
                    escalated=escalated,
                    lead_captured=lead_captured,
                )

            if response.stop_reason == "tool_use":
                tool_blocks = [b for b in response.content if b.type == "tool_use"]
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in tool_blocks:
                    result = await self._execute_tool(block.name, dict(block.input))
                    last_tool = block.name
                    if block.name == "capture_lead":
                        lead_captured = True
                    if block.name == "escalate":
                        escalated = True
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                messages.append({"role": "user", "content": tool_results})
                iteration += 1

                if total_output_tokens >= MAX_OUTPUT_TOKENS:
                    break
            else:
                break

        # Iteration or token cap reached — escalate gracefully
        logger.warning(
            "agent cap reached after %d iterations / %d tokens",
            iteration,
            total_output_tokens,
        )
        escalate_tool = self._tools["escalate"]
        await escalate_tool(reason="Agent iteration or token limit reached")
        return AgentResult(
            response=_FALLBACK_TEXT,
            tool_used="escalate",
            escalated=True,
            lead_captured=lead_captured,
        )
