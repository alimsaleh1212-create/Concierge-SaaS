"""Retriever rail checks for RAG chunks before prompt insertion."""

from __future__ import annotations

from dataclasses import dataclass

from app.constants import SAFE_REFUSAL
from app.schemas import RailsRetrievalRequest, RetrievedChunk
from app.services.platform_checks import classify_platform_output_fallback
from app.services.tenant_checks import _contains_topic


@dataclass(frozen=True)
class RetrievalCheckResult:
    allowed: bool
    filtered_chunks: list[RetrievedChunk]
    blocked_chunk_ids: list[str]
    reason: str | None
    refusal_message: str | None


def _chunk_id(chunk: RetrievedChunk) -> str:
    return f"{chunk.content_id}:{chunk.chunk_index}"


def _classify_retrieved_chunk(request: RailsRetrievalRequest, chunk: RetrievedChunk) -> str | None:
    platform_reason = classify_platform_output_fallback(chunk.text)
    if platform_reason:
        return platform_reason

    if any(_contains_topic(chunk.text, topic) for topic in request.tenant_rails.blocked_topics):
        return "off_topic"

    allowed_topics = request.tenant_rails.allowed_topics
    if allowed_topics and not any(_contains_topic(chunk.text, topic) for topic in allowed_topics):
        return "off_topic"

    return None


def check_retrieval(request: RailsRetrievalRequest) -> RetrievalCheckResult:
    filtered_chunks: list[RetrievedChunk] = []
    blocked_chunk_ids: list[str] = []
    first_reason: str | None = None

    for chunk in request.chunks:
        reason = _classify_retrieved_chunk(request, chunk)
        if reason:
            blocked_chunk_ids.append(_chunk_id(chunk))
            first_reason = first_reason or reason
            continue
        filtered_chunks.append(chunk)

    if filtered_chunks:
        return RetrievalCheckResult(
            allowed=True,
            filtered_chunks=filtered_chunks,
            blocked_chunk_ids=blocked_chunk_ids,
            reason=None,
            refusal_message=None,
        )

    if blocked_chunk_ids:
        return RetrievalCheckResult(
            allowed=False,
            filtered_chunks=[],
            blocked_chunk_ids=blocked_chunk_ids,
            reason=first_reason,
            refusal_message=SAFE_REFUSAL,
        )

    return RetrievalCheckResult(
        allowed=True,
        filtered_chunks=[],
        blocked_chunk_ids=[],
        reason=None,
        refusal_message=None,
    )
