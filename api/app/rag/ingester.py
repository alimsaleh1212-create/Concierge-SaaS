import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.chunker import chunk
from app.rag.embedder import embed_chunks
from app.repositories.embedding_repo import EmbeddingRepository


async def ingest_content(
    content_id: uuid.UUID,
    tenant_id: uuid.UUID,
    body: str,
    session: AsyncSession,
) -> int:
    """Chunk, embed, and upsert all chunks for a CMS content item.

    Returns the number of chunks written.
    """
    chunks = chunk(body)
    if not chunks:
        return 0

    embeddings = await embed_chunks([c.child_text for c in chunks])
    repo = EmbeddingRepository(session)

    for c, emb in zip(chunks, embeddings):
        await repo.insert_chunk(
            content_id=content_id,
            tenant_id=tenant_id,
            chunk_text=c.child_text,
            parent_chunk_text=c.parent_text,
            chunk_index=c.chunk_index,
            embedding=emb,
        )

    return len(chunks)
