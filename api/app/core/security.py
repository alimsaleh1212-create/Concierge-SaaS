from dataclasses import dataclass

import bcrypt
import jwt
from fastapi import HTTPException, status

from app.core.config import get_settings

# bcrypt hard-limits passwords to 72 bytes — encode + truncate explicitly
_BCRYPT_MAX = 72


def get_password_hash(password: str) -> str:
    secret = password.encode("utf-8")[:_BCRYPT_MAX]
    return bcrypt.hashpw(secret, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    secret = plain.encode("utf-8")[:_BCRYPT_MAX]
    return bcrypt.checkpw(secret, hashed.encode("utf-8"))


@dataclass
class TokenClaims:
    user_id: str
    tenant_id: str | None
    role: str
    email: str


@dataclass
class WidgetTokenClaims:
    tenant_id: str
    widget_id: str
    # session_id is a client-supplied body field per contract, not a JWT claim


def verify_admin_token(token: str) -> TokenClaims:
    """Verify a fastapi-users JWT. Raises HTTP 401 on any failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    return TokenClaims(
        user_id=payload["sub"],
        tenant_id=payload.get("tenant_id"),
        role=payload.get("role", ""),
        email=payload.get("email", ""),
    )


def verify_widget_token(token: str) -> WidgetTokenClaims:
    """Verify a short-lived visitor JWT. Returns tenant_id and widget_id from claims only.

    FR-014: tenant_id must never come from the request body. Raises HTTP 401 on invalid token.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid widget token") from exc

    return WidgetTokenClaims(
        tenant_id=payload["tenant_id"],
        widget_id=payload["widget_id"],
    )


def verify_service_token(token: str, expected: str) -> None:
    """Verify an opaque service-to-service bearer token. Raises HTTP 401 on mismatch."""
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token")
