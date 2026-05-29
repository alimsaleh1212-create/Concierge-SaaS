"""Classifier eval gate — CI gate for FR-027 / T-C007 / T-C014.

Loads evals/classifier/test_set.csv, classifies each row via the modelserver
POST /classify endpoint, computes macro-F1, and asserts it meets the threshold
in eval_thresholds.yaml (classifier.macro_f1 >= 0.70).

Requirements:
- Modelserver running at MODELSERVER_URL (default: http://localhost:8001)
- MODELSERVER_SERVICE_TOKEN env var or resolvable via Vault

Tests skip gracefully when the modelserver is not available.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import httpx
import pytest
import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODELSERVER_URL = os.getenv("MODELSERVER_URL", "http://localhost:8001").rstrip("/")
SERVICE_TOKEN = os.getenv("MODELSERVER_SERVICE_TOKEN", "")

THRESHOLDS_FILE = Path(__file__).parents[3] / "eval_thresholds.yaml"
TEST_SET_FILE = Path(__file__).parents[3] / "evals" / "classifier" / "test_set.csv"

_CONNECT_TIMEOUT = 3.0
_REQUEST_TIMEOUT = 10.0


def _load_threshold() -> float:
    try:
        with THRESHOLDS_FILE.open() as fh:
            data = yaml.safe_load(fh)
        return float(data["classifier"]["macro_f1"])
    except Exception:
        return 0.70  # spec floor


def _load_test_set() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with TEST_SET_FILE.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            text = (row.get("text") or "").strip()
            label = (row.get("label") or "").strip()
            if text and label:
                rows.append((text, label))
    return rows


def _get_service_token() -> str:
    if SERVICE_TOKEN:
        return SERVICE_TOKEN
    try:
        import urllib.request
        import json

        vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200")
        vault_token = os.getenv("VAULT_ROOT_TOKEN", "dev-root-token")
        req = urllib.request.Request(
            f"{vault_addr}/v1/secret/data/concierge",
            headers={"X-Vault-Token": vault_token},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
        return data["data"]["data"].get("MODELSERVER_SERVICE_TOKEN", "")
    except Exception:
        return ""


def _macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true))
    f1s: list[float] = []
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_classifier_macro_f1_meets_threshold() -> None:
    """Classifier macro-F1 on the held-out test set must meet the eval_thresholds floor."""
    token = _get_service_token()
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=_CONNECT_TIMEOUT) as probe:
            probe.get(f"{MODELSERVER_URL}/health")
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip(
            f"Modelserver not reachable at {MODELSERVER_URL} — "
            "run `docker compose up` to execute the classifier eval."
        )

    test_rows = _load_test_set()
    assert len(test_rows) > 0, f"Test set is empty — check {TEST_SET_FILE}"

    y_true: list[str] = []
    y_pred: list[str] = []

    with httpx.Client(base_url=MODELSERVER_URL, timeout=_REQUEST_TIMEOUT) as client:
        for text, label in test_rows:
            resp = client.post("/classify", json={"text": text}, headers=headers)
            if resp.status_code == 401:
                pytest.skip(
                    "Modelserver returned 401 — set MODELSERVER_SERVICE_TOKEN "
                    "or ensure Vault is running with the correct secret."
                )
            resp.raise_for_status()
            predicted = resp.json().get("label", "")
            y_true.append(label)
            y_pred.append(predicted)

    threshold = _load_threshold()
    macro_f1 = _macro_f1(y_true, y_pred)

    assert macro_f1 >= threshold, (
        f"\n[CLASSIFIER GATE FAIL] macro-F1 below threshold.\n"
        f"  Computed : {macro_f1:.4f}\n"
        f"  Threshold: {threshold:.4f}\n"
        f"  Rows     : {len(y_true)}"
    )
