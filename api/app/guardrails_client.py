"""HTTP client for the guardrails sidecar."""
import logging
import uuid
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT = 3.0
_RETRY_STATUS_CODES = {503}
_DEFAULT_CONVERSATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
_DEFAULT_TENANT_RAILS = {
    "allowed_topics": [],
    "blocked_topics": [],
    "refusal_tone": None,
}


async def check_input(
    text: str,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    tenant_rails: dict[str, Any] | None = None,
) -> bool:
    """Return True if the input should be blocked. Fail closed on sidecar errors."""
    return await _check_rails(
        endpoint="input",
        text=text,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        tenant_rails=tenant_rails,
    )


async def check_output(
    text: str,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    tenant_rails: dict[str, Any] | None = None,
) -> bool:
    """Return True if the output should be blocked. Fail closed on sidecar errors."""
    return await _check_rails(
        endpoint="output",
        text=text,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        tenant_rails=tenant_rails,
    )


async def _check_rails(
    *,
    endpoint: str,
    text: str,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    tenant_rails: dict[str, Any] | None,
) -> bool:
    settings = get_settings()
    service_token = settings.GUARDRAILS_SERVICE_TOKEN
    if not service_token:
        logger.error("guardrails service token is not configured, blocking request")
        return True

    base_url = settings.GUARDRAILS_BASE_URL.rstrip("/")
    payload = {
        "tenant_id": str(tenant_id),
        "conversation_id": str(conversation_id or _DEFAULT_CONVERSATION_ID),
        "content": text,
        "tenant_rails": tenant_rails or _DEFAULT_TENANT_RAILS,
    }
    headers = {"Authorization": f"Bearer {service_token}"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await _post_with_retry(
                client,
                f"{base_url}/rails/{endpoint}",
                payload,
                headers,
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("guardrails %s check unavailable or invalid, blocking: %s", endpoint, exc)
        return True

    allowed = body.get("allowed")
    if not isinstance(allowed, bool):
        logger.warning("guardrails %s check returned invalid allowed field, blocking", endpoint)
        return True

    return not allowed


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> httpx.Response:
    response = await client.post(url, json=payload, headers=headers)
    if response.status_code in _RETRY_STATUS_CODES:
        response = await client.post(url, json=payload, headers=headers)
    return response
