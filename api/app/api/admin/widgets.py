import secrets
import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, set_tenant_context
from app.repositories.base import BaseRepository
from app.models.widget import Widget
from app.services.auth_service import require_role

router = APIRouter(prefix="/admin/widgets", tags=["admin"])

_tenant_admin = require_role("tenant_admin")

_TopicStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
_ToneStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


def _tenant_id(current_user: dict) -> uuid.UUID:
    return uuid.UUID(current_user["tenant_id"])


class TenantRailsConfig(BaseModel):
    """Typed validation for tenant-editable guardrail settings stored in widgets.theme_config."""
    model_config = ConfigDict(extra="forbid")

    allowed_topics: list[_TopicStr] = Field(default_factory=list, max_length=50)
    blocked_topics: list[_TopicStr] = Field(default_factory=list, max_length=50)
    refusal_tone: Optional[_ToneStr] = None

    @field_validator("allowed_topics", "blocked_topics")
    @classmethod
    def dedupe(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for v in values:
            key = v.casefold()
            if key not in seen:
                seen.add(key)
                out.append(v)
        return out


class ThemeConfig(BaseModel):
    """Wraps theme_config JSONB. Validates tenant_rails if present; passes other keys through."""
    model_config = ConfigDict(extra="allow")

    tenant_rails: Optional[TenantRailsConfig] = None


class WidgetCreateRequest(BaseModel):
    name: str
    allowed_origins: list[str] = []
    greeting: Optional[str] = None
    theme_config: ThemeConfig = Field(default_factory=ThemeConfig)


class WidgetUpdateRequest(BaseModel):
    name: Optional[str] = None
    allowed_origins: Optional[list[str]] = None
    greeting: Optional[str] = None
    theme_config: Optional[ThemeConfig] = None


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
        "theme_config": body.theme_config.model_dump(exclude_none=True),
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
    raw = body.model_dump()
    if raw.get("theme_config") is not None and body.theme_config is not None:
        raw["theme_config"] = body.theme_config.model_dump(exclude_none=True)
    data = {k: v for k, v in raw.items() if v is not None}
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
