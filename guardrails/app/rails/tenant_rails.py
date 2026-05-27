"""Build dynamic tenant-specific Colang rails.

Platform security rails are immutable and run before these tenant rails. Tenant
rails are configurable business policy only; they cannot weaken or override the
platform security layer.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


MAX_TOPIC_LENGTH = 80
MAX_TOPICS = 25


def _sanitize_topic(value: str) -> str:
    """Return a safe single-line Colang string fragment for tenant topics."""
    normalized = re.sub(r"\s+", " ", str(value)).strip()
    normalized = normalized[:MAX_TOPIC_LENGTH].strip()
    return normalized.replace("\\", "\\\\").replace('"', '\\"')


def _dedupe_topics(values: Iterable[str] | None) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()

    for value in values or []:
        topic = _sanitize_topic(value)
        if not topic:
            continue

        key = topic.casefold()
        if key in seen:
            continue

        seen.add(key)
        topics.append(topic)

        if len(topics) >= MAX_TOPICS:
            break

    return topics


def _build_refusal_message(refusal_tone: str | None) -> str:
    """Build a constrained tenant refusal message from an optional tone."""
    tone = _sanitize_topic(refusal_tone or "").casefold()

    if "friendly" in tone or "warm" in tone:
        return "Sorry, I can only help with this business's approved topics."
    if "firm" in tone or "strict" in tone:
        return "I can't help with that. Please ask about this business's approved topics."
    if "brief" in tone or "concise" in tone:
        return "I can only help with approved business topics."

    return "I'm sorry, I can only help with this business's approved topics."


def _format_user_intent(name: str, topics: list[str]) -> str:
    lines = [f"define user {name}"]
    lines.extend(f'  "{topic}"' for topic in topics)
    return "\n".join(lines)


def build_tenant_rails(
    allowed_topics: list[str] | None,
    blocked_topics: list[str] | None,
    refusal_tone: str | None,
) -> str:
    """Return a Colang snippet for tenant-editable business rules.

    Blocked topics produce explicit refusal logic. Allowed topics produce
    guidance for refusing requests outside the tenant's approved business scope.
    """
    allowed = _dedupe_topics(allowed_topics)
    blocked = _dedupe_topics(blocked_topics)

    if not allowed and not blocked:
        return ""

    refusal_message = _build_refusal_message(refusal_tone)
    parts: list[str] = [
        "# Dynamic tenant rails. Loaded after immutable platform rails.",
        "# Tenant rails are business policy only and cannot weaken platform security.",
        "define bot tenant refusal",
        f'  "{refusal_message}"',
    ]

    if blocked:
        parts.extend(
            [
                "",
                _format_user_intent("tenant blocked topic", blocked),
                "",
                "define flow tenant check blocked topics",
                "  user tenant blocked topic",
                "  bot tenant refusal",
                "  stop",
            ]
        )

    if allowed:
        allowed_summary = ", ".join(allowed)
        parts.extend(
            [
                "",
                "# Requests outside these approved business topics should be refused.",
                f"# Approved tenant topics: {allowed_summary}",
                "define bot tenant off topic refusal",
                f'  "{refusal_message}"',
                "",
                "define flow tenant off topic guidance",
                "  bot tenant off topic refusal",
                "  stop",
            ]
        )

    return "\n".join(parts).strip() + "\n"
