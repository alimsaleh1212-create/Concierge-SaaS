import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.tenant_repo import TenantRepository
from app.services import tenant_service, erasure_service, cost_service
from app.services.auth_service import require_role

router = APIRouter(prefix="/platform/tenants", tags=["platform"])

_tenant_manager = require_role("tenant_manager")


class ProvisionRequest(BaseModel):
    name: str
    slug: str
    allowed_origins: list[str] = []


class InviteRequest(BaseModel):
    email: str


class SuspendRequest(BaseModel):
    reason: str = ""


def _actor_id(current_user: dict) -> uuid.UUID:
    return uuid.UUID(current_user["sub"])


@router.post("", status_code=201)
async def provision_tenant(
    body: ProvisionRequest,
    current_user: dict = Depends(_tenant_manager),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tenant = await tenant_service.provision_tenant(
        session, _actor_id(current_user), body.name, body.slug, body.allowed_origins
    )
    await session.commit()
    return {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug, "is_active": tenant.is_active}


@router.post("/{tenant_id}/invite", status_code=200)
async def invite_admin(
    tenant_id: uuid.UUID,
    body: InviteRequest,
    current_user: dict = Depends(_tenant_manager),
    session: AsyncSession = Depends(get_db),
) -> dict:
    user = await tenant_service.invite_admin(
        session, _actor_id(current_user), tenant_id, body.email
    )
    await session.commit()
    return {"status": "invited", "email": user.email}


@router.patch("/{tenant_id}/suspend", status_code=200)
async def suspend_tenant(
    tenant_id: uuid.UUID,
    body: SuspendRequest,
    current_user: dict = Depends(_tenant_manager),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tenant = await tenant_service.suspend_tenant(
        session, _actor_id(current_user), tenant_id
    )
    await session.commit()
    return {"id": str(tenant.id), "is_active": tenant.is_active}


@router.delete("/{tenant_id}", status_code=200)
async def erase_tenant(
    tenant_id: uuid.UUID,
    current_user: dict = Depends(_tenant_manager),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await erasure_service.erase_tenant(session, _actor_id(current_user), tenant_id)
    await session.commit()
    return {
        "status": "erased",
        "tenant_id": str(tenant_id),
        "stores_purged": ["redis", "pgvector", "minio", "postgres"],
    }


@router.get("", status_code=200)
async def list_tenants(
    current_user: dict = Depends(_tenant_manager),
    session: AsyncSession = Depends(get_db),
) -> dict:
    repo = TenantRepository(session)
    tenants = await repo.list_active()
    result = []
    for t in tenants:
        usage = await cost_service.get_cost_usage(session, t.id)
        result.append({
            "id": str(t.id),
            "slug": t.slug,
            "name": t.name,
            "is_active": t.is_active,
            "cost_7d_usd": usage.cost_7d_usd,
            "message_count_7d": usage.message_count,
        })
    return {"tenants": result}
