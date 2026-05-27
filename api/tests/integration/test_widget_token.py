import os
import time
import uuid

import httpx
import jwt
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@marios.example")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "pizza123")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000")
WIDGET_SECRET = os.getenv("TEST_WIDGET_SECRET")


def _request_client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=10)


def _login(client: httpx.Client) -> str | None:
    response = client.post(
        "/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        return None
    return response.json().get("access_token")


def _get_widget_id(client: httpx.Client, token: str) -> str | None:
    response = client.get(
        "/admin/widgets",
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code != 200:
        return None
    widgets = response.json().get("widgets", [])
    if not widgets:
        return None
    return widgets[0].get("id")


def _skip_if_unavailable(response: httpx.Response) -> None:
    if response.status_code == 404:
        pytest.skip("Endpoint not available in current app wiring")


def test_widget_token_ok() -> None:
    with _request_client() as client:
        token = _login(client)
        if not token:
            pytest.skip("Login unavailable; requires Owner A auth service")
        widget_id = _get_widget_id(client, token)
        if not widget_id:
            pytest.skip("No widget available; requires seeded widget data")

        response = client.post(
            "/auth/widget-token",
            json={"widget_id": widget_id, "origin": ALLOWED_ORIGIN},
        )
        _skip_if_unavailable(response)
        assert response.status_code == 200
        payload = response.json()
        assert payload.get("token")
        assert payload.get("expires_in") == 3600


def test_widget_token_disallowed_origin() -> None:
    with _request_client() as client:
        token = _login(client)
        if not token:
            pytest.skip("Login unavailable; requires Owner A auth service")
        widget_id = _get_widget_id(client, token)
        if not widget_id:
            pytest.skip("No widget available; requires seeded widget data")

        response = client.post(
            "/auth/widget-token",
            json={"widget_id": widget_id, "origin": "http://not-allowed.local"},
        )
        _skip_if_unavailable(response)
        assert response.status_code == 403


def test_widget_token_unknown_widget() -> None:
    with _request_client() as client:
        response = client.post(
            "/auth/widget-token",
            json={"widget_id": str(uuid.uuid4()), "origin": ALLOWED_ORIGIN},
        )
        _skip_if_unavailable(response)
        assert response.status_code == 404


def test_chat_missing_token() -> None:
    with _request_client() as client:
        response = client.post(
            "/chat/messages",
            json={"conversation_id": "new", "content": "Hi", "session_id": "test"},
        )
        if response.status_code == 404:
            pytest.skip("Chat route not mounted; depends on Owner B")
        assert response.status_code == 401


def test_chat_expired_token() -> None:
    if not WIDGET_SECRET:
        pytest.skip("TEST_WIDGET_SECRET not set; cannot mint expired token")

    with _request_client() as client:
        token = _login(client)
        if not token:
            pytest.skip("Login unavailable; requires Owner A auth service")
        widget_id = _get_widget_id(client, token)
        if not widget_id:
            pytest.skip("No widget available; requires seeded widget data")

        exchange = client.post(
            "/auth/widget-token",
            json={"widget_id": widget_id, "origin": ALLOWED_ORIGIN},
        )
        _skip_if_unavailable(exchange)
        assert exchange.status_code == 200

        raw = jwt.decode(exchange.json()["token"], options={"verify_signature": False})
        expired_token = jwt.encode(
            {
                "tenant_id": raw.get("tenant_id"),
                "widget_id": raw.get("widget_id"),
                "origin": raw.get("origin"),
                "iat": int(time.time()) - 7200,
                "exp": int(time.time()) - 3600,
            },
            WIDGET_SECRET,
            algorithm="HS256",
        )

        response = client.post(
            "/chat/messages",
            headers={"Authorization": f"Bearer {expired_token}"},
            json={"conversation_id": "new", "content": "Hi", "session_id": "test"},
        )
        if response.status_code == 404:
            pytest.skip("Chat route not mounted; depends on Owner B")
        assert response.status_code == 401
