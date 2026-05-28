"""FastAPI guardrails sidecar app wiring."""

from __future__ import annotations

from fastapi import FastAPI

from app.routers.health import router as health_router
from app.routers.rails import router as rails_router


app = FastAPI(title="Concierge Guardrails Sidecar")
app.include_router(health_router)
app.include_router(rails_router)
