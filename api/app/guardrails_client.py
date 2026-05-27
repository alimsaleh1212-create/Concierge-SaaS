"""Stub guardrails client — replace when Owner C delivers the NeMo sidecar."""
import logging
import uuid

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GUARDRAILS_URL = "http://guardrails:8002"
_TIMEOUT = 3.0


async def check_input(text: str, tenant_id: uuid.UUID) -> bool:
    """Return True if the input should be blocked. Fails open on sidecar errors."""
    try:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_GUARDRAILS_URL}/rails/input",
                json={"text": text, "tenant_id": str(tenant_id)},
                headers={"Authorization": f"Bearer {settings.GUARDRAILS_SERVICE_TOKEN}"},
            )
            resp.raise_for_status()
            return resp.json().get("blocked", False)
    except httpx.HTTPError as exc:
        logger.warning("guardrails input check unavailable, allowing: %s", exc)
        return False


async def check_output(text: str, tenant_id: uuid.UUID) -> bool:
    """Return True if the output should be blocked. Fails open on sidecar errors."""
    try:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_GUARDRAILS_URL}/rails/output",
                json={"text": text, "tenant_id": str(tenant_id)},
                headers={"Authorization": f"Bearer {settings.GUARDRAILS_SERVICE_TOKEN}"},
            )
            resp.raise_for_status()
            return resp.json().get("blocked", False)
    except httpx.HTTPError as exc:
        logger.warning("guardrails output check unavailable, allowing: %s", exc)
        return False
