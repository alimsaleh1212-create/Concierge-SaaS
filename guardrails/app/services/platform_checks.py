"""Platform guardrail checks and deterministic fallback classifiers."""

from __future__ import annotations

from collections.abc import Iterable

from app.constants import (
    CROSS_TENANT_INPUT_PHRASES,
    CROSS_TENANT_OUTPUT_PHRASES,
    JAILBREAK_PHRASES,
    PROMPT_INJECTION_PHRASES,
    SAFE_OUTPUT_FALLBACK,
    SAFE_REFUSAL,
    SYSTEM_PROMPT_INPUT_PHRASES,
    SYSTEM_PROMPT_OUTPUT_PHRASES,
)
from app.nemo_runtime import NemoCheckResult, get_nemo_runtime


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    normalized = _normalize(text)
    return any(phrase in normalized for phrase in phrases)


def classify_platform_input_fallback(content: str) -> str | None:
    """Deterministic fallback and reason mapping for platform input rails."""
    if _contains_any(content, PROMPT_INJECTION_PHRASES):
        return "prompt_injection_detected"
    if _contains_any(content, JAILBREAK_PHRASES):
        return "jailbreak_detected"
    if _contains_any(content, CROSS_TENANT_INPUT_PHRASES):
        return "cross_tenant_attempt"
    if _contains_any(content, SYSTEM_PROMPT_INPUT_PHRASES):
        return "system_prompt_extraction"
    return None


def classify_platform_output_fallback(content: str) -> str | None:
    """Deterministic fallback and reason mapping for platform output rails."""
    if _contains_any(content, CROSS_TENANT_OUTPUT_PHRASES):
        return "cross_tenant_attempt"
    if _contains_any(content, SYSTEM_PROMPT_OUTPUT_PHRASES):
        return "system_prompt_extraction"
    return None


def run_nemo_platform_check(content: str, direction: str) -> NemoCheckResult:
    return get_nemo_runtime().check(content, direction)  # type: ignore[arg-type]


def check_platform_input(content: str) -> tuple[str, str] | None:
    """Run immutable platform input checks before tenant-editable rails."""
    nemo_result = run_nemo_platform_check(content, "input")
    if nemo_result.blocked:
        return (
            classify_platform_input_fallback(content) or "prompt_injection_detected",
            nemo_result.content or SAFE_REFUSAL,
        )

    reason = classify_platform_input_fallback(content)
    if reason:
        return reason, SAFE_REFUSAL

    return None


def check_platform_output(content: str) -> tuple[str, str, str] | None:
    """Run immutable platform output checks before returning model text."""
    nemo_result = run_nemo_platform_check(content, "output")
    if nemo_result.blocked:
        return (
            classify_platform_output_fallback(content) or "cross_tenant_attempt",
            SAFE_REFUSAL,
            SAFE_OUTPUT_FALLBACK,
        )

    reason = classify_platform_output_fallback(content)
    if reason:
        return reason, SAFE_REFUSAL, SAFE_OUTPUT_FALLBACK

    return None
