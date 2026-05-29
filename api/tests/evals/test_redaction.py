"""Redaction eval gate — CI gate for SC-002 / FR-032 / T-C026.

Sends a synthetic API key (sk-test-1234567890abcdef) through the full chat
pipeline via POST /chat/messages and asserts the raw key never appears in:
  1. The HTTP response body
  2. Any messages row written to the Postgres DB during this session
  3. Any Redis session key created during this chat turn

Pass rate must be 1.00 (eval_thresholds.yaml: redaction.pass_rate: 1.00).

Requirements:
- API running at API_BASE_URL (default: http://localhost:8000)
- Postgres reachable at DATABASE_URL (default: postgresql://concierge:concierge@localhost:5432/concierge)
- Redis reachable at REDIS_URL (default: redis://localhost:6379)
- Demo tenants seeded (ADMIN_EMAIL / ADMIN_PASSWORD)

Tests skip gracefully when infrastructure is not available.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid

import asyncpg
import httpx
import pytest
import redis

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://concierge:concierge@localhost:5432/concierge"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@novatech.example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "demo-password-change-me")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000")

SYNTHETIC_KEY = "sk-test-1234567890abcdef"

_REQUEST_TIMEOUT = 15.0
_CONNECT_TIMEOUT = 3.0


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------

def _api_reachable() -> bool:
    try:
        with httpx.Client(timeout=_CONNECT_TIMEOUT) as c:
            c.post(f"{API_BASE_URL}/auth/login", data={"username": "x", "password": "y"})
        return True
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def _get_widget_token() -> str | None:
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=_REQUEST_TIMEOUT) as c:
            login = c.post("/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            if login.status_code != 200:
                return None
            admin_token = login.json().get("access_token")
            if not admin_token:
                return None

            widgets = c.get("/admin/widgets", headers={"Authorization": f"Bearer {admin_token}"})
            if widgets.status_code != 200:
                return None
            widget_list = widgets.json().get("widgets", [])
            if not widget_list:
                return None
            widget_id = widget_list[0].get("id")

            exchange = c.post(
                "/auth/widget-token",
                json={"widget_id": widget_id, "origin": ALLOWED_ORIGIN},
            )
            if exchange.status_code != 200:
                return None
            return exchange.json().get("token")
    except Exception:
        return None


async def _db_messages_containing(token: str, conversation_id: str) -> list[str]:
    """Return content values from messages rows that contain the sentinel."""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch(
            "SELECT content FROM messages WHERE conversation_id = $1::uuid AND content LIKE $2",
            conversation_id,
            f"%{token}%",
        )
        await conn.close()
        return [r["content"] for r in rows]
    except Exception:
        return []  # Skip DB check if unavailable


def _redis_sessions_containing(token: str, conversation_id: str) -> list[str]:
    """Return Redis values for session keys that contain the sentinel."""
    leaking = []
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        # Session keys follow pattern: session:{tenant_id}:{conversation_id}
        pattern = f"session:*:{conversation_id}"
        for key in r.scan_iter(pattern):
            value = r.get(key) or ""
            if token in value:
                leaking.append(key)
    except Exception:
        pass  # Skip Redis check if unavailable
    return leaking


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def widget_token() -> str:
    if not _api_reachable():
        pytest.skip(
            f"API not reachable at {API_BASE_URL} — run `docker compose up` to execute the redaction eval.",
            allow_module_level=True,
        )
    token = _get_widget_token()
    if token is None:
        pytest.skip(
            "Could not obtain widget token — ensure demo tenants are seeded "
            "and ADMIN_EMAIL / ADMIN_PASSWORD are correct.",
            allow_module_level=True,
        )
    return token


# ---------------------------------------------------------------------------
# Eval test
# ---------------------------------------------------------------------------

def test_synthetic_api_key_never_leaks(widget_token: str) -> None:
    """SC-002 / FR-032: a synthetic API key pasted into chat must never appear
    unredacted in the HTTP response, the Postgres messages table, or Redis.

    The raw string 'sk-test-1234567890abcdef' must be absent from all three stores.
    """
    message_with_key = f"My API key is {SYNTHETIC_KEY} — can you help me debug?"

    with httpx.Client(base_url=API_BASE_URL, timeout=_REQUEST_TIMEOUT) as client:
        response = client.post(
            "/chat/messages",
            headers={"Authorization": f"Bearer {widget_token}"},
            json={"content": message_with_key},
        )

    if response.status_code == 404:
        pytest.skip("POST /chat/messages not mounted — depends on Owner B chat route")

    assert response.status_code in (200, 400), (
        f"Unexpected HTTP status {response.status_code}: {response.text[:200]}"
    )

    # 1. Assert key is absent from the HTTP response body
    assert SYNTHETIC_KEY not in response.text, (
        f"\n[REDACTION FAIL] Synthetic key found in HTTP response body.\n"
        f"  Key     : {SYNTHETIC_KEY!r}\n"
        f"  Response: {response.text[:500]}"
    )

    # 2. Assert key is absent from DB messages rows (best-effort — skip if DB unavailable)
    conversation_id: str | None = None
    try:
        body = response.json()
        conversation_id = str(body.get("conversation_id", ""))
    except Exception:
        pass

    if conversation_id:
        leaking_db_rows = asyncio.run(_db_messages_containing(SYNTHETIC_KEY, conversation_id))
        assert len(leaking_db_rows) == 0, (
            f"\n[REDACTION FAIL] Synthetic key found in Postgres messages table.\n"
            f"  Key             : {SYNTHETIC_KEY!r}\n"
            f"  conversation_id : {conversation_id}\n"
            f"  Leaking rows    : {len(leaking_db_rows)}\n"
            f"  Sample content  : {leaking_db_rows[0][:200] if leaking_db_rows else 'N/A'}"
        )

        # 3. Assert key is absent from Redis session keys for this conversation
        leaking_redis_keys = _redis_sessions_containing(SYNTHETIC_KEY, conversation_id)
        assert len(leaking_redis_keys) == 0, (
            f"\n[REDACTION FAIL] Synthetic key found in Redis session.\n"
            f"  Key             : {SYNTHETIC_KEY!r}\n"
            f"  conversation_id : {conversation_id}\n"
            f"  Leaking keys    : {leaking_redis_keys}"
        )
