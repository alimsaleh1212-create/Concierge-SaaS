"""FR-014 enforcement — verify_widget_token must source tenant_id and widget_id
from the signed JWT only, never from the request body.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException


def _make_widget_token(tenant_id: str, widget_id: str, secret: str) -> str:
    payload = {
        "tenant_id": tenant_id,
        "widget_id": widget_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class FakeSettings:
    JWT_SECRET = "test-secret-for-unit-test"


def test_verify_widget_token_returns_claims_from_jwt():
    """Claims must be sourced from the JWT — tenant_id and widget_id, no session_id."""
    from app.core.security import verify_widget_token, WidgetTokenClaims
    from app.core import security as sec_mod

    secret = FakeSettings.JWT_SECRET
    tenant_id = str(uuid.uuid4())
    widget_id = str(uuid.uuid4())

    token = _make_widget_token(tenant_id, widget_id, secret)

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(sec_mod, "get_settings", lambda: FakeSettings())
        claims = verify_widget_token(token)

    assert isinstance(claims, WidgetTokenClaims)
    assert claims.tenant_id == tenant_id
    assert claims.widget_id == widget_id
    assert not hasattr(claims, "session_id"), "session_id must not be a JWT claim"


def test_verify_widget_token_raises_401_on_invalid_token():
    """A garbage token must raise HTTP 401."""
    from app.core.security import verify_widget_token
    from app.core import security as sec_mod

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(sec_mod, "get_settings", lambda: FakeSettings())
        with pytest.raises(HTTPException) as exc_info:
            verify_widget_token("not.a.valid.jwt")

    assert exc_info.value.status_code == 401


def test_verify_widget_token_raises_401_on_expired_token():
    """An expired JWT must raise HTTP 401."""
    from app.core.security import verify_widget_token
    from app.core import security as sec_mod

    secret = FakeSettings.JWT_SECRET
    payload = {
        "tenant_id": str(uuid.uuid4()),
        "widget_id": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    expired_token = jwt.encode(payload, secret, algorithm="HS256")

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(sec_mod, "get_settings", lambda: FakeSettings())
        with pytest.raises(HTTPException) as exc_info:
            verify_widget_token(expired_token)

    assert exc_info.value.status_code == 401
