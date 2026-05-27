import asyncio
import logging
import uuid
from typing import Any

import anthropic

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 2000
_MAX_ATTEMPTS = 3

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(
            api_key=get_settings().ANTHROPIC_API_KEY,
            timeout=30.0,
        )
    return _client


async def chat_completion(
    messages: list[dict[str, Any]],
    system: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    tools: list[dict[str, Any]] | None = None,
    tenant_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
) -> anthropic.types.Message:
    """Call Claude with retry (3 attempts, exponential backoff) and token logging."""
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = await get_client().messages.create(**kwargs)
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
        except (anthropic.RateLimitError, anthropic.APIStatusError) as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(2**attempt)
        except anthropic.APIConnectionError as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(2**attempt)

    raise last_exc  # type: ignore[misc]
