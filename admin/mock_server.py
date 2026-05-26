from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WIDGET_LOADER = ROOT / "widget" / "loader" / "widget.js"
WIDGET_BUNDLE = ROOT / "widget" / "dist" / "index.js"

ALLOWED_ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000"}

STATE = {
    "cms": [],
    "widgets": [],
    "leads": [
        {
            "id": str(uuid.uuid4()),
            "name": "Alex Customer",
            "email": "alex@example.com",
            "status": "new",
            "message": "Interested in a demo",
        }
    ],
}


def _fake_jwt(claims: dict[str, Any]) -> str:
    header = {"alg": "none", "typ": "JWT"}
    header_b64 = _urlsafe_b64(json.dumps(header).encode("utf-8"))
    payload_b64 = _urlsafe_b64(json.dumps(claims).encode("utf-8"))
    return f"{header_b64}.{payload_b64}."


def _urlsafe_b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    data = handler.rfile.read(length)
    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def _serve_js(handler: BaseHTTPRequestHandler, content: bytes) -> None:
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "application/javascript")
    handler.send_header("Content-Length", str(len(content)))
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(content)


class MockHandler(BaseHTTPRequestHandler):
    server_version = "ConciergeMock/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "service": "concierge-mock",
                    "status": "ok",
                    "endpoints": [
                        "/health",
                        "/auth/login",
                        "/auth/widget-token",
                        "/admin/cms",
                        "/admin/widgets",
                        "/admin/widgets/{id}/snippet",
                        "/admin/leads",
                        "/chat/messages",
                        "/widget.js",
                        "/widget-bundle/index.js",
                    ],
                },
            )
            return
        if self.path == "/health":
            _json_response(self, HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/widget.js":
            content = WIDGET_LOADER.read_bytes() if WIDGET_LOADER.exists() else b"console.log('mock widget loader');"
            _serve_js(self, content)
            return
        if self.path == "/widget-bundle/index.js":
            content = WIDGET_BUNDLE.read_bytes() if WIDGET_BUNDLE.exists() else b"document.body.innerHTML='Mock widget bundle';"
            _serve_js(self, content)
            return
        if self.path == "/admin/cms":
            _json_response(self, HTTPStatus.OK, {"items": STATE["cms"]})
            return
        if self.path == "/admin/widgets":
            _json_response(self, HTTPStatus.OK, {"widgets": STATE["widgets"]})
            return
        if self.path.startswith("/admin/widgets/") and self.path.endswith("/snippet"):
            widget_id = self.path.split("/")[3]
            snippet = (
                f"<script src=\"http://localhost:9000/widget.js\" data-widget-id=\"{widget_id}\"></script>"
            )
            _json_response(self, HTTPStatus.OK, {"snippet": snippet})
            return
        if self.path.startswith("/admin/leads"):
            _json_response(self, HTTPStatus.OK, {"leads": STATE["leads"]})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/auth/login":
            now = int(time.time())
            token = _fake_jwt(
                {
                    "sub": "user-1",
                    "tenant_id": str(uuid.uuid4()),
                    "role": "tenant_admin",
                    "email": "admin@marios.example",
                    "iat": now,
                    "exp": now + 3600,
                }
            )
            _json_response(self, HTTPStatus.OK, {"access_token": token, "token_type": "bearer"})
            return
        if self.path == "/auth/widget-token":
            payload = _read_body(self)
            origin = payload.get("origin")
            if origin not in ALLOWED_ORIGINS:
                _json_response(self, HTTPStatus.FORBIDDEN, {"detail": "Origin not allowed"})
                return
            _json_response(self, HTTPStatus.OK, {"token": "mock-widget-token", "expires_in": 3600})
            return
        if self.path == "/admin/cms":
            payload = _read_body(self)
            item = {
                "id": str(uuid.uuid4()),
                "title": payload.get("title", ""),
                "body": payload.get("body", ""),
                "content_type": payload.get("content_type", "faq"),
                "metadata": payload.get("metadata") or {},
            }
            STATE["cms"].append(item)
            _json_response(self, HTTPStatus.OK, item)
            return
        if self.path == "/admin/widgets":
            payload = _read_body(self)
            widget = {
                "id": str(uuid.uuid4()),
                "name": payload.get("name", "Widget"),
                "greeting": payload.get("greeting"),
                "allowed_origins": payload.get("allowed_origins") or [],
                "theme_config": payload.get("theme_config") or {},
            }
            STATE["widgets"].append(widget)
            _json_response(self, HTTPStatus.OK, widget)
            return
        if self.path == "/chat/messages":
            payload = _read_body(self)
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "conversation_id": payload.get("conversation_id") or "new",
                    "response": "This is a mock response.",
                    "tool_used": "mock",
                    "escalated": False,
                    "lead_captured": False,
                },
            )
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_PATCH(self) -> None:  # noqa: N802
        if self.path.startswith("/admin/cms/"):
            item_id = self.path.split("/")[-1]
            payload = _read_body(self)
            for item in STATE["cms"]:
                if item["id"] == item_id:
                    item.update({k: v for k, v in payload.items() if v is not None})
                    _json_response(self, HTTPStatus.OK, item)
                    return
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        if self.path.startswith("/admin/widgets/"):
            widget_id = self.path.split("/")[-1]
            payload = _read_body(self)
            for widget in STATE["widgets"]:
                if widget["id"] == widget_id:
                    widget.update({k: v for k, v in payload.items() if v is not None})
                    _json_response(self, HTTPStatus.OK, widget)
                    return
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        if self.path.startswith("/admin/leads/"):
            lead_id = self.path.split("/")[-1]
            payload = _read_body(self)
            for lead in STATE["leads"]:
                if lead["id"] == lead_id:
                    if "status" in payload:
                        lead["status"] = payload["status"]
                    _json_response(self, HTTPStatus.OK, lead)
                    return
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path.startswith("/admin/cms/"):
            item_id = self.path.split("/")[-1]
            STATE["cms"] = [item for item in STATE["cms"] if item["id"] != item_id]
            _json_response(self, HTTPStatus.OK, {"status": "deleted"})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        if os.getenv("MOCK_VERBOSE"):
            super().log_message(format, *args)


def run(host: str = "0.0.0.0", port: int = 9000) -> None:
    server = ThreadingHTTPServer((host, port), MockHandler)
    print(f"Mock server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
