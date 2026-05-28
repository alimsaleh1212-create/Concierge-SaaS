"""Adapter between RAG retrieval results and Retriever Rails."""
import uuid
from typing import Any

from app import guardrails_client
from app.rag.retriever import ParentChunk

_DEFAULT_TENANT_RAILS = {
    "allowed_topics": [],
    "blocked_topics": [],
    "refusal_tone": None,
}


def chunks_to_guardrails_payload(chunks: list[ParentChunk]) -> list[dict[str, Any]]:
    return [
        {
            "content_id": str(chunk.content_id),
            "chunk_index": chunk.chunk_index,
            "text": chunk.parent_text,
        }
        for chunk in chunks
    ]


async def apply_retrieval_guardrails(
    *,
    query: str,
    chunks: list[ParentChunk],
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    tenant_rails: dict[str, Any] | None = None,
) -> list[ParentChunk]:
    if not chunks:
        return []

    result = await guardrails_client.check_retrieval(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        query=query,
        chunks=chunks_to_guardrails_payload(chunks),
        tenant_rails=tenant_rails or default_tenant_rails(),
    )
    if not result.allowed:
        return []

    chunks_by_key = {
        _chunk_key(chunk.content_id, chunk.chunk_index): chunk
        for chunk in chunks
    }

    safe_chunks: list[ParentChunk] = []
    for filtered_chunk in result.filtered_chunks:
        key = _chunk_key(filtered_chunk.get("content_id"), filtered_chunk.get("chunk_index"))
        chunk = chunks_by_key.get(key)
        if chunk is not None:
            safe_chunks.append(chunk)
    return safe_chunks


def default_tenant_rails() -> dict[str, Any]:
    return dict(_DEFAULT_TENANT_RAILS)


def _chunk_key(content_id: Any, chunk_index: Any) -> tuple[str, int] | None:
    try:
        return (str(content_id), int(chunk_index))
    except (TypeError, ValueError):
        return None
