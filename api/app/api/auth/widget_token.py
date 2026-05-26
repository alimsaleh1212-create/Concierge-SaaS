from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.tenant import Tenant
from app.models.widget import Widget


class WidgetTokenRequest(BaseModel):
    widget_id: UUID
    origin: str


class WidgetTokenResponse(BaseModel):
    token: str
    expires_in: int


router = APIRouter(prefix="/auth", tags=["auth"])

try:
    from app.services.auth_service import auth_backend, fastapi_users

    router.include_router(fastapi_users.get_auth_router(auth_backend), prefix="")
except Exception:
    # Auth service is wired by Owner A; keep widget-token endpoint available meanwhile.
    pass


@router.post("/widget-token", response_model=WidgetTokenResponse)
async def create_widget_token(
    payload: WidgetTokenRequest,
    session: AsyncSession = Depends(get_db),
) -> WidgetTokenResponse:
    widget_result = await session.execute(
        select(Widget).filter(
            Widget.id == payload.widget_id,
            Widget.is_active == True,  # noqa: E712
            Widget.is_deleted == False,  # noqa: E712
        )
    )
    widget = widget_result.scalar_one_or_none()
    if widget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")

    tenant_result = await session.execute(
        select(Tenant).filter(
            Tenant.id == widget.tenant_id,
            Tenant.is_active == True,  # noqa: E712
            Tenant.is_deleted == False,  # noqa: E712
        )
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")

    allowed_origins = set(widget.allowed_origins or []) | set(tenant.allowed_origins or [])
    if payload.origin not in allowed_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed")

    expires_in = 3600
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "tenant_id": str(widget.tenant_id),
            "widget_id": str(widget.id),
            "origin": payload.origin,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        },
        widget.widget_token_secret,
        algorithm="HS256",
    )

    return WidgetTokenResponse(token=token, expires_in=expires_in)
