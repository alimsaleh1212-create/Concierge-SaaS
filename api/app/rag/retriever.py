import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedder import embed_query, rerank as voyage_rerank
from app.core.llm import chat_completion
from app.repositories.embedding_repo import EmbeddingRepository

logger = logging.getLogger(__name__)

# Fetch 3x candidates before reranking so the reranker has a meaningful pool.
_RERANK_FETCH_MULTIPLIER = 3


@dataclass
class ParentChunk:
    chunk_index: int
    child_text: str
    parent_text: str
    content_id: uuid.UUID


async def retrieve(
    query: str,
    tenant_id: uuid.UUID,
    session: AsyncSession,
    top_k: int = 5,
) -> list[ParentChunk]:
    """Return top-k parent chunks for query, scoped to tenant_id.

    Active improvement: reranking (voyage-rerank-2).
    Both candidates were measured on the 15-triple golden set — see DECISIONS.md.
    """
    return await _retrieve_with_rerank(query, tenant_id, session, top_k)


# ── T-B032: Reranking branch (WINNER) ────────────────────────────────────────

async def _retrieve_with_rerank(
    query: str,
    tenant_id: uuid.UUID,
    session: AsyncSession,
    top_k: int = 5,
) -> list[ParentChunk]:
    """Fetch top-N candidates via cosine search then rerank to top-k.

    Fetching more candidates than needed gives the reranker a meaningful pool
    to reorder. Falls back to cosine order if the Voyage rerank call fails.
    """
    fetch_k = top_k * _RERANK_FETCH_MULTIPLIER
    query_vec = await embed_query(query)
    repo = EmbeddingRepository(session)
    rows = await repo.cosine_search(query_vec, tenant_id, fetch_k)

    if not rows:
        return []

    documents = [row.chunk_text for row in rows]
    try:
        ranked_indices = await voyage_rerank(query, documents, top_k=min(top_k, len(rows)))
        rows = [rows[i] for i in ranked_indices]
    except Exception as exc:
        logger.warning("rerank failed (%s), using cosine order", exc)
        rows = rows[:top_k]

    return [
        ParentChunk(
            chunk_index=row.chunk_index,
            child_text=row.chunk_text,
            parent_text=row.parent_chunk_text,
            content_id=row.content_id,
        )
        for row in rows
    ]


# ── T-B033: Query-rewriting branch (measured, not active) ────────────────────

async def _retrieve_with_query_rewrite(
    query: str,
    tenant_id: uuid.UUID,
    session: AsyncSession,
    top_k: int = 5,
) -> list[ParentChunk]:
    """Rewrite the query via Claude before embedding, then cosine-search.

    Scored lower than reranking on the 15-triple golden set — see DECISIONS.md.
    Kept here for reference; not called by retrieve().
    """
    response = await chat_completion(
        messages=[{"role": "user", "content": query}],
        system=(
            "Rewrite the user's question to be clearer and more specific for searching "
            "a business FAQ knowledge base. Return only the rewritten question, no explanation."
        ),
        max_tokens=128,
    )
    rewritten = next(
        (b.text for b in response.content if b.type == "text"), query
    ).strip()
    logger.debug("query rewrite: %r → %r", query, rewritten)

    query_vec = await embed_query(rewritten)
    repo = EmbeddingRepository(session)
    rows = await repo.cosine_search(query_vec, tenant_id, top_k)

    return [
        ParentChunk(
            chunk_index=row.chunk_index,
            child_text=row.chunk_text,
            parent_text=row.parent_chunk_text,
            content_id=row.content_id,
        )
        for row in rows
    ]
