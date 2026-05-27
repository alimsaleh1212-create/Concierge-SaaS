import json
import uuid
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

_SESSION_TTL = 1800  # 30 minutes rolling window

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _client


def _key(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> str:
    return f"session:{tenant_id}:{conversation_id}"


async def get_session(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> list[dict[str, Any]] | None:
    raw = await get_client().get(_key(tenant_id, conversation_id))
    if raw is None:
        return None
    return json.loads(raw)


async def set_session(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    messages: list[dict[str, Any]],
) -> None:
    await get_client().setex(
        _key(tenant_id, conversation_id),
        _SESSION_TTL,
        json.dumps(messages),
    )


async def delete_session(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    await get_client().delete(_key(tenant_id, conversation_id))
