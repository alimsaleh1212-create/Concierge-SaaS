import secrets
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, set_tenant_context
from app.repositories.base import BaseRepository
from app.models.widget import Widget
from app.services.auth_service import require_role

router = APIRouter(prefix="/admin/widgets", tags=["admin"])

_tenant_admin = require_role("tenant_admin")


def _tenant_id(current_user: dict) -> uuid.UUID:
    return uuid.UUID(current_user["tenant_id"])


class WidgetCreateRequest(BaseModel):
    name: str
    allowed_origins: list[str] = []
    greeting: Optional[str] = None
    theme_config: dict = {}


class WidgetUpdateRequest(BaseModel):
    name: Optional[str] = None
    allowed_origins: Optional[list[str]] = None
    greeting: Optional[str] = None
    theme_config: Optional[dict] = None


def _widget_repo(session: AsyncSession) -> BaseRepository:
    return BaseRepository(Widget, session)


@router.get("", status_code=200)
async def list_widgets(
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    await set_tenant_context(session, tid)
    repo = _widget_repo(session)
    widgets = await repo.all(tid)
    return {
        "widgets": [
            {"id": str(w.id), "name": w.name, "is_active": w.is_active}
            for w in widgets
        ]
    }


@router.post("", status_code=201)
async def create_widget(
    body: WidgetCreateRequest,
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    await set_tenant_context(session, tid)
    repo = _widget_repo(session)
    widget = await repo.create({
        "tenant_id": tid,
        "name": body.name,
        "widget_token_secret": secrets.token_hex(32),  # always generated server-side
        "allowed_origins": body.allowed_origins,
        "greeting": body.greeting,
        "theme_config": body.theme_config,
    })
    await session.commit()
    return {"id": str(widget.id), "name": widget.name}


@router.patch("/{widget_id}", status_code=200)
async def update_widget(
    widget_id: uuid.UUID,
    body: WidgetUpdateRequest,
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    await set_tenant_context(session, tid)
    repo = _widget_repo(session)
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    widget = await repo.update(widget_id, data, tid)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    await session.commit()
    return {"id": str(widget.id), "name": widget.name}


@router.get("/{widget_id}/snippet", status_code=200)
async def get_snippet(
    widget_id: uuid.UUID,
    current_user: dict = Depends(_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = _tenant_id(current_user)
    await set_tenant_context(session, tid)
    repo = _widget_repo(session)
    widget = await repo.get(widget_id, tid)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    snippet = (
        f'<script src="http://localhost:8000/static/widget.js" '
        f'data-widget-id="{widget_id}"></script>'
    )
    return {"snippet": snippet, "widget_id": str(widget_id)}
