import uuid
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.cms_content import CmsContent
from app.models.embedding import Embedding
from app.repositories.cms_repo import CmsRepository


async def create_content(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    data: dict[str, Any],
    background_tasks: BackgroundTasks | None = None,
) -> CmsContent:
    repo = CmsRepository(session)
    content = await repo.create({"tenant_id": tenant_id, **data})
    if background_tasks is not None:
        background_tasks.add_task(_ingest_embeddings, content.id, tenant_id)
    return content


async def update_content(
    session: AsyncSession,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    data: dict[str, Any],
    background_tasks: BackgroundTasks | None = None,
) -> CmsContent | None:
    repo = CmsRepository(session)
    content = await repo.update(id, data, tenant_id)
    if content and "body" in data and background_tasks is not None:
        # Re-trigger embedding ingestion when body changes
        background_tasks.add_task(_ingest_embeddings, content.id, tenant_id)
    return content


async def soft_delete_content(
    session: AsyncSession,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> bool:
    repo = CmsRepository(session)
    deleted = await repo.soft_delete(id, tenant_id)
    if deleted:
        # Hard-delete all linked embedding rows — no orphan vectors
        await session.execute(
            delete(Embedding).where(
                Embedding.content_id == id,
                Embedding.tenant_id == tenant_id,
            )
        )
        await session.flush()
    return deleted


async def _ingest_embeddings(content_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Fire-and-forget background task: chunk, embed, and upsert vectors for a content item."""
    from app.rag.ingester import ingest_content

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CmsContent).where(CmsContent.id == content_id, CmsContent.is_deleted == False)  # noqa: E712
        )
        content = result.scalar_one_or_none()
        if content is None:
            return
        await ingest_content(content_id, tenant_id, content.body, session)
        await session.commit()
