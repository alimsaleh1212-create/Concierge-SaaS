import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.repositories.base import BaseRepository


class TenantRepository(BaseRepository[Tenant]):
    """Platform-level repository — not scoped by tenant_id."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tenant, session)

    async def all(self, tenant_id: uuid.UUID | None = None) -> list[Tenant]:  # type: ignore[override]
        result = await self.session.execute(
            select(Tenant).filter(Tenant.is_deleted == False)  # noqa: E712
        )
        return list(result.scalars().all())

    async def get(self, id: uuid.UUID, tenant_id: uuid.UUID | None = None) -> Tenant | None:  # type: ignore[override]
        result = await self.session.execute(
            select(Tenant).filter(Tenant.id == id, Tenant.is_deleted == False)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(
            select(Tenant).filter(Tenant.slug == slug, Tenant.is_deleted == False)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Tenant]:
        result = await self.session.execute(
            select(Tenant).filter(Tenant.is_active == True, Tenant.is_deleted == False)  # noqa: E712
        )
        return list(result.scalars().all())

    async def suspend(self, id: uuid.UUID) -> Tenant | None:
        tenant = await self.get(id)
        if tenant is None:
            return None
        tenant.is_active = False
        await self.session.flush()
        await self.session.refresh(tenant)
        return tenant

    async def hard_delete(self, id: uuid.UUID) -> bool:
        tenant = await self.get(id)
        if tenant is None:
            return False
        await self.session.delete(tenant)
        await self.session.flush()
        return True
