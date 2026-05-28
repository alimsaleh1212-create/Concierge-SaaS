"""Tenant-configurable business-topic checks."""

from __future__ import annotations

from app.rails.tenant_rails import build_tenant_rails
from app.schemas import RailsInputRequest
from app.services.platform_checks import _normalize


def _contains_topic(text: str, topic: str) -> bool:
    normalized_text = _normalize(text)
    normalized_topic = _normalize(topic)
    return bool(normalized_topic) and normalized_topic in normalized_text


def check_tenant_input(request: RailsInputRequest) -> str | None:
    # Build the dynamic snippet so tenant rail generation remains connected here.
    build_tenant_rails(
        request.tenant_rails.allowed_topics,
        request.tenant_rails.blocked_topics,
        request.tenant_rails.refusal_tone,
    )

    if any(_contains_topic(request.content, topic) for topic in request.tenant_rails.blocked_topics):
        return "off_topic"

    allowed_topics = request.tenant_rails.allowed_topics
    if allowed_topics and not any(_contains_topic(request.content, topic) for topic in allowed_topics):
        return "off_topic"

    return None
