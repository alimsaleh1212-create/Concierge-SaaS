from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

try:
    from .startup import MODEL_FILENAME, verify_model_artifact
except ImportError:  # Allows `python modelserver/app/classifier.py` from repo root.
    from startup import MODEL_FILENAME, verify_model_artifact


_MODEL: Any | None = None


def _modelserver_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _artifact_path() -> Path:
    return _modelserver_dir() / "artifacts" / MODEL_FILENAME


def _load_model() -> Any:
    global _MODEL

    if _MODEL is None:
        verify_model_artifact()
        _MODEL = joblib.load(_artifact_path())

    return _MODEL


def _confidence_for_label(model: Any, text: str, label: str) -> float:
    if not hasattr(model, "predict_proba"):
        return 1.0

    probabilities = model.predict_proba([text])[0]
    classes = [str(candidate) for candidate in getattr(model, "classes_", [])]

    if classes and label in classes:
        return float(probabilities[classes.index(label)])

    return float(max(probabilities))


def predict(text: str) -> tuple[str, float]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    model = _load_model()
    label = str(model.predict([text])[0])
    confidence = _confidence_for_label(model, text, label)

    return label, confidence


if __name__ == "__main__":
    print(predict("Can someone contact me about pricing?"))
