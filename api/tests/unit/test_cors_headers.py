import os

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@marios.example")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "pizza123")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000")


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


def _assert_cors_csp(response: httpx.Response) -> None:
    allow_origin = response.headers.get("Access-Control-Allow-Origin")
    csp = response.headers.get("Content-Security-Policy")
    assert allow_origin == ALLOWED_ORIGIN
    assert csp and "frame-ancestors" in csp


def test_admin_routes_emit_cors_csp() -> None:
    with _request_client() as client:
        token = _login(client)
        if not token:
            pytest.skip("Login unavailable; requires Owner A auth service")

        response = client.get(
            "/admin/widgets",
            headers={"Authorization": f"Bearer {token}", "Origin": ALLOWED_ORIGIN},
        )
        if response.status_code == 404:
            pytest.skip("Admin routes not mounted; depends on Owner A")
        _assert_cors_csp(response)


def test_chat_routes_emit_cors_csp() -> None:
    with _request_client() as client:
        response = client.post(
            "/chat/messages",
            headers={"Authorization": "Bearer invalid", "Origin": ALLOWED_ORIGIN},
            json={"conversation_id": "new", "content": "Hi", "session_id": "test"},
        )
        if response.status_code == 404:
            pytest.skip("Chat route not mounted; depends on Owner B")
        _assert_cors_csp(response)
