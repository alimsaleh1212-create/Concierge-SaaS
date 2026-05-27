import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MODELSERVER_URL = "http://modelserver:8001"
_TIMEOUT = 5.0


@dataclass
class ClassifyResult:
    label: str
    confidence: float


async def classify(text: str) -> ClassifyResult:
    """POST /classify to modelserver. Falls back to label='unknown' if unreachable."""
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.MODELSERVER_SERVICE_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{MODELSERVER_URL}/classify",
                json={"text": text},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return ClassifyResult(label=data["label"], confidence=data["confidence"])
    except httpx.HTTPError as exc:
        logger.warning("modelserver unreachable, using fallback: %s", exc)
        return ClassifyResult(label="unknown", confidence=0.0)
