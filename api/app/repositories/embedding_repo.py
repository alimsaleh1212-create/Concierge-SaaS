import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import Embedding


class EmbeddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_chunk(
        self,
        *,
        content_id: uuid.UUID,
        tenant_id: uuid.UUID,
        chunk_text: str,
        parent_chunk_text: str,
        chunk_index: int,
        embedding: list[float],
    ) -> Embedding:
        row = Embedding(
            content_id=content_id,
            tenant_id=tenant_id,
            chunk_text=chunk_text,
            parent_chunk_text=parent_chunk_text,
            chunk_index=chunk_index,
            embedding=embedding,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def cosine_search(
        self,
        query_vec: list[float],
        tenant_id: uuid.UUID,
        top_k: int = 5,
    ) -> list[Embedding]:
        """Return top-k chunks by cosine similarity, tenant_id filtered inside the scan."""
        stmt = (
            select(Embedding)
            .where(Embedding.tenant_id == tenant_id)
            .order_by(Embedding.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_content(self, content_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
        """Hard-delete all chunks for a content item. Returns deleted row count."""
        result = await self.session.execute(
            select(Embedding).where(
                Embedding.content_id == content_id,
                Embedding.tenant_id == tenant_id,
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)
