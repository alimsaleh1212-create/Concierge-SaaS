"""Service-token authentication for guardrails endpoints."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.config import get_guardrails_service_token


def _require_service_token(authorization: str | None = Header(default=None)) -> None:
    expected_token = get_guardrails_service_token()
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GUARDRAILS_SERVICE_TOKEN is not configured",
        )

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed bearer token",
        )

    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
