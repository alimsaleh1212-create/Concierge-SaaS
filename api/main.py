from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.api.platform import tenants as platform_tenants
from app.api.platform import audit as platform_audit
from app.api.admin import cms as admin_cms
from app.api.admin import widgets as admin_widgets
from app.api.admin import leads as admin_leads
from app.agent.router import validate_prompts
from app.api.auth import widget_token as auth_widget_token
from app.api.chat import messages as chat_messages
from app.core.config import get_settings
from app.core.tracing import setup_tracing
from app.middleware.rate_limit import TenantRateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Settings loaded here to surface Vault errors at startup, not at first request
    get_settings()
    validate_prompts()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Concierge API", version="0.1.0", lifespan=lifespan)
    setup_tracing(app)

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(platform_tenants.router)
    app.include_router(platform_audit.router)
    app.include_router(admin_cms.router)
    app.include_router(admin_widgets.router)
    app.include_router(admin_leads.router)
    app.include_router(chat_messages.router)
    app.include_router(auth_widget_token.router)

    # ── Health ─────────────────────────────────────────────────────────────────
    @app.get("/health", tags=["internal"])
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    # ── Prometheus metrics ─────────────────────────────────────────────────────
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # ── Rate limiting middleware ────────────────────────────────────────────────
    settings = get_settings()
    app.add_middleware(TenantRateLimitMiddleware, redis_url=settings.REDIS_URL)

    return app


app = create_app()
