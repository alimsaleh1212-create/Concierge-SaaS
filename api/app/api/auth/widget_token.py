from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_password
from app.models.tenant import Tenant
from app.models.user import User
from app.models.widget import Widget
from app.services.auth_service import create_access_token


class WidgetTokenRequest(BaseModel):
    widget_id: UUID
    origin: str


class WidgetTokenResponse(BaseModel):
    token: str
    expires_in: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Email + password → JWT bearer token.

    Native replacement for the fastapi-users `/auth/login` route. Accepts the
    OAuth2 password-flow form (`username`, `password`) so Swagger's "Authorize"
    button and the Streamlit admin can both use it. See DECISIONS.md D-012.
    """
    result = await session.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or user.is_deleted
        or not verify_password(form.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return LoginResponse(access_token=create_access_token(user), token_type="bearer")


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
