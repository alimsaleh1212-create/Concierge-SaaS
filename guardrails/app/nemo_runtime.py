"""Runtime adapter for NeMo Guardrails platform rails."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

os.environ.setdefault("NEMOGUARDRAILS_LLM_FRAMEWORK", "langchain")

from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.llm.frameworks import set_default_framework


GuardrailsDirection = Literal["input", "output"]
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"


@dataclass(frozen=True)
class NemoCheckResult:
    available: bool
    blocked: bool
    content: str | None = None


class NemoRuntime:
    """Lazy NeMo runtime for immutable platform rails."""

    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self._config_path = project_root / "config" / "config.yml"
        self._platform_rails_path = project_root / "app" / "rails" / "platform_rails.co"
        self._rails: LLMRails | None = None
        self._load_error: Exception | None = None

    @property
    def status(self) -> str:
        return "fallback" if self._load_error else "loaded"

    def check(self, content: str, direction: GuardrailsDirection) -> NemoCheckResult:
        try:
            rails = self._get_rails()
            if not os.getenv(ANTHROPIC_API_KEY_ENV):
                raise RuntimeError(f"{ANTHROPIC_API_KEY_ENV} is not configured")
            result = rails.generate(
                messages=[
                    {"role": "user", "content": self._format_prompt(content, direction)},
                ]
            )
        except Exception as exc:
            self._load_error = exc
            return NemoCheckResult(available=False, blocked=False)

        generated = self._extract_content(result)
        if not generated:
            return NemoCheckResult(available=True, blocked=False)

        if self._looks_like_refusal(generated):
            return NemoCheckResult(available=True, blocked=True, content=generated)

        return NemoCheckResult(available=True, blocked=False, content=generated)

    def _get_rails(self) -> LLMRails:
        if self._rails is None:
            set_default_framework("langchain")
            config = RailsConfig.from_content(
                yaml_content=self._config_path.read_text(encoding="utf-8"),
                colang_content=self._platform_rails_path.read_text(encoding="utf-8"),
            )
            self._rails = LLMRails(config)
            self._load_error = None

        return self._rails

    @staticmethod
    def _format_prompt(content: str, direction: GuardrailsDirection) -> str:
        if direction == "output":
            return f"Check this generated response for platform rail violations:\n{content}"

        return content

    @staticmethod
    def _extract_content(result: object) -> str:
        if isinstance(result, str):
            return result

        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, str):
                return content

            messages = result.get("messages")
            if isinstance(messages, list) and messages:
                last = messages[-1]
                if isinstance(last, dict) and isinstance(last.get("content"), str):
                    return last["content"]

        return ""

    @staticmethod
    def _looks_like_refusal(content: str) -> bool:
        normalized = content.casefold()
        return any(
            phrase in normalized
            for phrase in (
                "can't help",
                "cannot help",
                "can not help",
                "i'm sorry",
                "not able to help",
                "cannot comply",
                "refuse",
            )
        )


_runtime = NemoRuntime()


def get_nemo_runtime() -> NemoRuntime:
    return _runtime
