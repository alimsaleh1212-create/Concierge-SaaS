from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


MODEL_FILENAME = "model.joblib"
MODEL_CARD_FILENAME = "model_card.md"
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")


class StartupVerificationError(RuntimeError):
    """Raised when the pinned model artifact cannot be verified."""


def _modelserver_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_expected_sha256(model_card_path: Path) -> str:
    if not model_card_path.is_file():
        raise StartupVerificationError(
            f"Model card is missing: {model_card_path}"
        )

    contents = model_card_path.read_text(encoding="utf-8")
    matches = SHA256_RE.findall(contents)
    if not matches:
        raise StartupVerificationError(
            f"SHA-256 hash is missing from model card: {model_card_path}"
        )

    return matches[0].lower()


def _compute_sha256(artifact_path: Path) -> str:
    if not artifact_path.is_file():
        raise StartupVerificationError(
            f"Model artifact is missing: {artifact_path}"
        )

    digest = hashlib.sha256()
    with artifact_path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def verify_model_artifact() -> str:
    modelserver_dir = _modelserver_dir()
    artifact_path = modelserver_dir / "artifacts" / MODEL_FILENAME
    model_card_path = modelserver_dir / "artifacts" / MODEL_CARD_FILENAME

    expected_sha256 = _read_expected_sha256(model_card_path)
    actual_sha256 = _compute_sha256(artifact_path)

    if actual_sha256 != expected_sha256:
        raise StartupVerificationError(
            "Model artifact SHA-256 mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    return actual_sha256


def main() -> int:
    try:
        verified_sha256 = verify_model_artifact()
    except StartupVerificationError as exc:
        print(f"startup verification failed: {exc}", file=sys.stderr)
        return 1

    print(verified_sha256)
    return 0


if __name__ == "__main__":
    sys.exit(main())
