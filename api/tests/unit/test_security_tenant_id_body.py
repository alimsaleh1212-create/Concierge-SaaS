"""T-A027: FR-014 enforcement — verify_widget_token must raise HTTP 403
when the tenant_id in the request body mismatches the JWT claim.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException


def _make_widget_token(tenant_id: str, widget_id: str, session_id: str, secret: str) -> str:
    payload = {
        "tenant_id": tenant_id,
        "widget_id": widget_id,
        "session_id": session_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_verify_widget_token_raises_403_on_tenant_mismatch():
    """A valid Tenant A JWT with Tenant B body tenant_id must raise HTTP 403."""
    from app.core.security import verify_widget_token

    secret = "test-secret-for-unit-test"
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    widget_id = str(uuid.uuid4())
    session_id = "test-session"

    token = _make_widget_token(tenant_a, widget_id, session_id, secret)

    with pytest.raises(HTTPException) as exc_info:
        with pytest.MonkeyPatch().context() as mp:
            # Patch the secret used in verify_widget_token
            from app.core import security as sec_mod
            original = sec_mod.get_settings

            class FakeSettings:
                ANTHROPIC_API_KEY = secret

            mp.setattr(sec_mod, "get_settings", lambda: FakeSettings())
            verify_widget_token(token, tenant_b)  # body says tenant_b, JWT says tenant_a

    assert exc_info.value.status_code == 403


def test_verify_widget_token_succeeds_on_tenant_match():
    """A valid JWT where tenant_id matches the body must succeed (no exception)."""
    from app.core.security import verify_widget_token

    secret = "test-secret-for-unit-test"
    tenant_id = str(uuid.uuid4())
    widget_id = str(uuid.uuid4())
    session_id = "test-session"

    token = _make_widget_token(tenant_id, widget_id, session_id, secret)

    from app.core import security as sec_mod

    class FakeSettings:
        ANTHROPIC_API_KEY = secret

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(sec_mod, "get_settings", lambda: FakeSettings())
        claims = verify_widget_token(token, tenant_id)

    assert claims.tenant_id == tenant_id
    assert claims.widget_id == widget_id


def test_verify_widget_token_raises_401_on_invalid_token():
    """A garbage token must raise HTTP 401."""
    from app.core.security import verify_widget_token
    from app.core import security as sec_mod

    class FakeSettings:
        ANTHROPIC_API_KEY = "any-secret"

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(sec_mod, "get_settings", lambda: FakeSettings())
        with pytest.raises(HTTPException) as exc_info:
            verify_widget_token("not.a.valid.jwt", "some-tenant")

    assert exc_info.value.status_code == 401
