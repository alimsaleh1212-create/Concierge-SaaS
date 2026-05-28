import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import AgentResult, TenantContext, ToolCallingAgent
from app.agent.tools.capture_lead import CaptureLeadTool
from app.agent.tools.escalate import EscalateTool
from app.core import modelserver_client
from app.core.llm import chat_completion
from app.rag.retrieval_guardrails import apply_retrieval_guardrails, default_tenant_rails
from app.rag.retriever import retrieve

logger = logging.getLogger(__name__)

# Confidence threshold — documented in DECISIONS.md
_HIGH_CONFIDENCE = 0.75

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_rag_answer_template: str | None = None

_REQUIRED_PROMPTS = ["system.md", "rag_answer.md", "capture_lead.md", "escalate.md"]


def validate_prompts() -> None:
    """Raise RuntimeError at startup if any required prompt file is missing or empty."""
    for name in _REQUIRED_PROMPTS:
        path = _PROMPTS_DIR / name
        if not path.exists():
            raise RuntimeError(f"Required prompt file not found: {path}")
        if not path.read_text(encoding="utf-8").strip():
            raise RuntimeError(f"Required prompt file is empty: {path}")


def _load_rag_answer() -> str:
    global _rag_answer_template
    if _rag_answer_template is None:
        _rag_answer_template = (_PROMPTS_DIR / "rag_answer.md").read_text(encoding="utf-8")
    return _rag_answer_template


async def route(
    message: str,
    messages: list[dict[str, Any]],
    tenant_ctx: TenantContext,
    session: AsyncSession,
) -> AgentResult:
    """Classify the message and dispatch to the appropriate workflow or agent."""
    result = await modelserver_client.classify(message)
    label, confidence = result.label, result.confidence

    logger.info(
        "router.classify label=%s confidence=%.3f", label, confidence
    )

    if label == "spam":
        return AgentResult(response="I'm sorry, I can only help with topics relevant to our business.")

    if confidence >= _HIGH_CONFIDENCE:
        if label == "support":
            return await _rag_workflow(message, messages, tenant_ctx, session)
        if label == "sales":
            return await _lead_workflow(message, tenant_ctx, session)
        if label == "escalate":
            return await _escalate_workflow(message, tenant_ctx, session)

    # Low confidence or unknown → full agent loop
    return await _agent_workflow(message, messages, tenant_ctx, session)


async def _rag_workflow(
    message: str,
    messages: list[dict[str, Any]],
    tenant_ctx: TenantContext,
    session: AsyncSession,
) -> AgentResult:
    """Deterministic: retrieve → prompt → Claude. No agent loop."""
    chunks = await retrieve(message, tenant_ctx.tenant_id, session, top_k=5)
    safe_chunks = await apply_retrieval_guardrails(
        query=message,
        chunks=chunks,
        tenant_id=tenant_ctx.tenant_id,
        conversation_id=tenant_ctx.conversation_id,
        tenant_rails=default_tenant_rails(),
    )
    if chunks and not safe_chunks:
        return AgentResult(
            response="I'm sorry, I can't use the retrieved context for this request.",
            tool_used="rag_search",
        )

    context = "\n\n".join(f"[{i+1}] {c.parent_text}" for i, c in enumerate(safe_chunks))

    prompt = (
        _load_rag_answer()
        .replace("{{context}}", context or "No relevant information found.")
        .replace("{{question}}", message)
    )

    response = await chat_completion(
        messages=messages + [{"role": "user", "content": prompt}],
        system=f"You are a helpful assistant for {tenant_ctx.tenant_name}.",
        max_tokens=1024,
        tenant_id=tenant_ctx.tenant_id,
        conversation_id=tenant_ctx.conversation_id,
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    return AgentResult(response=text, tool_used="rag_search")


async def _lead_workflow(
    message: str,
    tenant_ctx: TenantContext,
    session: AsyncSession,
) -> AgentResult:
    """Deterministic: ask for contact details and call capture_lead."""
    capture = CaptureLeadTool(
        tenant_ctx.tenant_id,
        tenant_ctx.conversation_id,
        session,
        visitor_ip=tenant_ctx.visitor_ip,
    )

    # Ask Claude to extract details and call the tool
    response = await chat_completion(
        messages=[{"role": "user", "content": message}],
        system=(
            (_PROMPTS_DIR / "capture_lead.md").read_text(encoding="utf-8")
        ),
        tools=[capture.schema],
        max_tokens=512,
        tenant_id=tenant_ctx.tenant_id,
        conversation_id=tenant_ctx.conversation_id,
    )

    lead_captured = False
    for block in response.content:
        if block.type == "tool_use" and block.name == "capture_lead":
            await capture(**dict(block.input))
            lead_captured = True

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        text = "Thank you! We've noted your interest and someone will be in touch soon."

    return AgentResult(response=text, tool_used="capture_lead", lead_captured=lead_captured)


async def _escalate_workflow(
    message: str,
    tenant_ctx: TenantContext,
    session: AsyncSession,
) -> AgentResult:
    """Deterministic: escalate immediately."""
    escalate = EscalateTool(tenant_ctx.tenant_id, tenant_ctx.conversation_id, session)
    await escalate(reason="Classifier routed to escalate with high confidence")

    escalate_text = (_PROMPTS_DIR / "escalate.md").read_text(encoding="utf-8")
    text = escalate_text.replace("{{tenant_name}}", tenant_ctx.tenant_name)
    return AgentResult(response=text, tool_used="escalate", escalated=True)


async def _agent_workflow(
    message: str,
    messages: list[dict[str, Any]],
    tenant_ctx: TenantContext,
    session: AsyncSession,
) -> AgentResult:
    """Full tool-calling agent loop for low-confidence or ambiguous messages."""
    agent = ToolCallingAgent(tenant_ctx, session)
    full_messages = messages + [{"role": "user", "content": message}]
    return await agent.run(full_messages)
