"""Groq chat-completion adapter.

Callers build requests and read responses in Anthropic Messages shape
(system prompt, content blocks, tool_use / tool_result, stop_reason). This
module translates that shape to Groq's OpenAI-compatible API and back, so the
agent, router and retriever stay provider-agnostic. See DECISIONS.md D-013.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import groq

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 2000
_MAX_ATTEMPTS = 3

# Groq finish_reason → Anthropic-style stop_reason expected by callers
_STOP_REASONS = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}

_client: groq.AsyncGroq | None = None


@dataclass
class TextBlock:
    text: str
    type: Literal["text"] = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: Literal["tool_use"] = "tool_use"


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    content: list[TextBlock | ToolUseBlock]
    stop_reason: str
    usage: Usage
    model: str = ""


def get_client() -> groq.AsyncGroq:
    global _client
    if _client is None:
        _client = groq.AsyncGroq(
            api_key=get_settings().GROQ_API_KEY,
            timeout=30.0,
        )
    return _client


def _block_get(block: Any, key: str) -> Any:
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)


def _to_groq_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic-style messages (str or content-block lists) to OpenAI format."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        role, content = message["role"], message["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        texts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in content:
            block_type = _block_get(block, "type")
            if block_type == "text":
                texts.append(_block_get(block, "text"))
            elif block_type == "tool_use":
                tool_calls.append({
                    "id": _block_get(block, "id"),
                    "type": "function",
                    "function": {
                        "name": _block_get(block, "name"),
                        "arguments": json.dumps(_block_get(block, "input") or {}),
                    },
                })
            elif block_type == "tool_result":
                result = _block_get(block, "content")
                out.append({
                    "role": "tool",
                    "tool_call_id": _block_get(block, "tool_use_id"),
                    "content": result if isinstance(result, str) else json.dumps(result),
                })

        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
        elif texts:
            out.append({"role": role, "content": "\n".join(texts)})
    return out


def _to_groq_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


def _from_groq_completion(completion: Any) -> LLMResponse:
    choice = completion.choices[0]
    blocks: list[TextBlock | ToolUseBlock] = []
    if choice.message.content:
        blocks.append(TextBlock(text=choice.message.content))
    for call in choice.message.tool_calls or []:
        blocks.append(
            ToolUseBlock(
                id=call.id,
                name=call.function.name,
                input=json.loads(call.function.arguments or "{}"),
            )
        )

    stop_reason = _STOP_REASONS.get(choice.finish_reason, choice.finish_reason)
    if choice.message.tool_calls:
        stop_reason = "tool_use"

    usage = completion.usage
    return LLMResponse(
        content=blocks,
        stop_reason=stop_reason,
        usage=Usage(
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        ),
        model=completion.model,
    )


async def chat_completion(
    messages: list[dict[str, Any]],
    system: str,
    *,
    model: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    tools: list[dict[str, Any]] | None = None,
    tenant_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
) -> LLMResponse:
    """Call Groq with retry (3 attempts, exponential backoff) and token logging."""
    model = model or get_settings().GROQ_MODEL
    kwargs: dict[str, Any] = {
        "model": model,
        "max_completion_tokens": max_tokens,
        "messages": _to_groq_messages(system, messages),
    }
    if tools:
        kwargs["tools"] = _to_groq_tools(tools)
    # gpt-oss models reason before answering and reasoning tokens count against
    # max_completion_tokens; keep it short so small budgets still yield an answer.
    if model.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = "low"

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            completion = await get_client().chat.completions.create(**kwargs)
            response = _from_groq_completion(completion)
            logger.info(
                "llm.call completed",
                extra={
                    "tenant_id": str(tenant_id),
                    "conversation_id": str(conversation_id),
                    "model": model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )
            return response
        except (groq.RateLimitError, groq.APIStatusError) as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(2**attempt)
        except groq.APIConnectionError as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(2**attempt)

    raise last_exc  # type: ignore[misc]
