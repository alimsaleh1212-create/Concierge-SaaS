import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.repositories.base import BaseRepository


class LeadRepository(BaseRepository[Lead]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Lead, session)

    async def list_by_status(self, tenant_id: uuid.UUID, status: str) -> list[Lead]:
        result = await self.session.execute(
            select(Lead).filter(
                Lead.tenant_id == tenant_id,
                Lead.status == status,
                Lead.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def update_status(self, id: uuid.UUID, status: str, tenant_id: uuid.UUID) -> Lead | None:
        return await self.update(id, {"status": status}, tenant_id)
