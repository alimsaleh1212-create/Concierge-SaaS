import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cms_content import CmsContent
from app.repositories.base import BaseRepository


class CmsRepository(BaseRepository[CmsContent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CmsContent, session)

    async def list_active(self, tenant_id: uuid.UUID) -> list[CmsContent]:
        result = await self.session.execute(
            select(CmsContent).filter(
                CmsContent.tenant_id == tenant_id,
                CmsContent.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def get_with_embeddings(self, id: uuid.UUID, tenant_id: uuid.UUID) -> CmsContent | None:
        result = await self.session.execute(
            select(CmsContent)
            .options(selectinload(CmsContent.embeddings))
            .filter(
                CmsContent.id == id,
                CmsContent.tenant_id == tenant_id,
                CmsContent.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()
