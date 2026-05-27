import uuid
from typing import Any

from app.core import session as redis_session

_DEFAULT_LAST_N = 10


async def get_session_history(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    last_n: int = _DEFAULT_LAST_N,
) -> list[dict[str, Any]]:
    """Return the last N messages from Redis for this conversation."""
    messages = await redis_session.get_session(tenant_id, conversation_id)
    if messages is None:
        return []
    return messages[-last_n:]


async def append_to_session(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
) -> None:
    """Append one message to the session and reset the TTL."""
    messages = await redis_session.get_session(tenant_id, conversation_id) or []
    messages.append({"role": role, "content": content})
    await redis_session.set_session(tenant_id, conversation_id, messages)
