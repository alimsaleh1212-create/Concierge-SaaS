"""Pydantic schemas for the guardrails sidecar contract."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


MAX_TOPIC_LENGTH = 80
MAX_REFUSAL_TONE_LENGTH = 80
MAX_CONTENT_LENGTH = 20_000
MAX_TOPICS = 50
MAX_RETRIEVED_CHUNKS = 20

GuardrailsReason = Literal[
    "prompt_injection_detected",
    "jailbreak_detected",
    "cross_tenant_attempt",
    "system_prompt_extraction",
    "off_topic",
]

TopicString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TOPIC_LENGTH),
]

ContentString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CONTENT_LENGTH),
]

RefusalTone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_REFUSAL_TONE_LENGTH),
]


class TenantRails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_topics: list[TopicString] = Field(default_factory=list, max_length=MAX_TOPICS)
    blocked_topics: list[TopicString] = Field(default_factory=list, max_length=MAX_TOPICS)
    refusal_tone: RefusalTone | None = None

    @field_validator("allowed_topics", "blocked_topics")
    @classmethod
    def dedupe_topics(cls, values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()

        for value in values:
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(value)

        return deduped


class _RailsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID | str
    conversation_id: UUID | str
    content: ContentString
    tenant_rails: TenantRails = Field(default_factory=TenantRails)


class RailsInputRequest(_RailsRequest):
    pass


class RailsOutputRequest(_RailsRequest):
    pass


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: UUID | str
    chunk_index: int = Field(ge=0)
    text: ContentString


class RailsRetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID | str
    conversation_id: UUID | str
    query: ContentString
    chunks: list[RetrievedChunk] = Field(default_factory=list, max_length=MAX_RETRIEVED_CHUNKS)
    tenant_rails: TenantRails = Field(default_factory=TenantRails)


class _RailsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    modified_content: str | None = None
    reason: GuardrailsReason | None = None
    refusal_message: str | None = None


class RailsInputResponse(_RailsResponse):
    pass


class RailsOutputResponse(_RailsResponse):
    pass


class RailsRetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    filtered_chunks: list[RetrievedChunk] = Field(default_factory=list, max_length=MAX_RETRIEVED_CHUNKS)
    blocked_chunk_ids: list[str] = Field(default_factory=list, max_length=MAX_RETRIEVED_CHUNKS)
    reason: GuardrailsReason | None = None
    refusal_message: str | None = None
