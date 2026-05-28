import logging
import uuid

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GUARDRAILS_URL = "http://guardrails:8002"
_TIMEOUT = 3.0


async def check_input(
    text: str,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    tenant_rails: dict | None = None,
) -> bool:
    """Return True if the input should be blocked. Fails open on sidecar errors."""
    try:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_GUARDRAILS_URL}/rails/input",
                json={
                    "content": text,
                    "tenant_id": str(tenant_id),
                    "conversation_id": str(conversation_id or uuid.uuid4()),
                    "tenant_rails": tenant_rails or {},
                },
                headers={"Authorization": f"Bearer {settings.GUARDRAILS_SERVICE_TOKEN}"},
            )
            resp.raise_for_status()
            return not resp.json().get("allowed", True)
    except httpx.HTTPError as exc:
        logger.warning("guardrails input check unavailable, allowing: %s", exc)
        return False


async def check_output(
    text: str,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
) -> bool:
    """Return True if the output should be blocked. Fails open on sidecar errors."""
    try:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_GUARDRAILS_URL}/rails/output",
                json={
                    "content": text,
                    "tenant_id": str(tenant_id),
                    "conversation_id": str(conversation_id or uuid.uuid4()),
                },
                headers={"Authorization": f"Bearer {settings.GUARDRAILS_SERVICE_TOKEN}"},
            )
            resp.raise_for_status()
            return not resp.json().get("allowed", True)
    except httpx.HTTPError as exc:
        logger.warning("guardrails output check unavailable, allowing: %s", exc)
        return False
