import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User
from app.models.audit_log import AuditLog
from app.repositories.tenant_repo import TenantRepository
from app.core.security import get_password_hash


async def provision_tenant(
    session: AsyncSession,
    actor_id: uuid.UUID,
    name: str,
    slug: str,
    allowed_origins: list[str],
) -> Tenant:
    repo = TenantRepository(session)
    tenant = await repo.create({
        "name": name,
        "slug": slug,
        "allowed_origins": allowed_origins,
    })
    session.add(AuditLog(
        actor_id=actor_id,
        actor_role="tenant_manager",
        tenant_id=tenant.id,
        action="tenant.created",
        metadata_={"slug": slug, "name": name},
    ))
    await session.flush()
    return tenant


async def invite_admin(
    session: AsyncSession,
    actor_id: uuid.UUID,
    tenant_id: uuid.UUID,
    email: str,
) -> User:
    user = User(
        tenant_id=tenant_id,
        email=email.lower(),
        hashed_password=get_password_hash("changeme"),  # placeholder — user sets via reset flow
        role="tenant_admin",
        is_active=False,
    )
    session.add(user)
    session.add(AuditLog(
        actor_id=actor_id,
        actor_role="tenant_manager",
        tenant_id=tenant_id,
        action="tenant.admin_invited",
        metadata_={"email": email},
    ))
    await session.flush()
    await session.refresh(user)
    return user


async def suspend_tenant(
    session: AsyncSession,
    actor_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Tenant:
    repo = TenantRepository(session)
    tenant = await repo.suspend(tenant_id)
    if tenant is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tenant not found")
    session.add(AuditLog(
        actor_id=actor_id,
        actor_role="tenant_manager",
        tenant_id=tenant_id,
        action="tenant.suspended",
        metadata_={},
    ))
    await session.flush()
    return tenant
