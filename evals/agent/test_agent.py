"""Agent tool-selection eval — accuracy against the 15-example golden set.

Mocks the classifier and all external I/O so the test runs fast with no live
services. What is measured: given a classifier label, does the router dispatch
to the correct tool? This is a regression guard for the router's dispatch logic.

Tool selection in production is driven almost entirely by the classifier (Owner C).
The mock test catches breakage in router.py; classifier accuracy is the real gate.

Classifier mock mapping:
  rag_search   → label="support",  confidence=0.9
  capture_lead → label="sales",    confidence=0.9
  escalate     → label="escalate", confidence=0.9
  null         → label="support",  confidence=0.4  (low-conf → agent loop → no tool)

Run from the api/ directory so pyproject.toml (asyncio_mode=auto) is picked up:
    cd api && pytest ../evals/agent/test_agent.py -v -s
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

_API_DIR = Path(__file__).parents[2] / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

_HERE = Path(__file__).parent
_REPO_ROOT = Path(__file__).parents[2]

GOLDEN_SET_PATH = _HERE / "golden_set.yaml"
THRESHOLDS_PATH = _REPO_ROOT / "eval_thresholds.yaml"

# Classifier mock values for each expected tool
_CLASSIFY_MAP = {
    "rag_search":   ("support",  0.9),
    "capture_lead": ("sales",    0.9),
    "escalate":     ("escalate", 0.9),
    None:           ("support",  0.4),  # low confidence → agent loop → no tool called
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_golden_set() -> list[dict]:
    with open(GOLDEN_SET_PATH) as f:
        return yaml.safe_load(f)["examples"]


def _load_thresholds() -> dict:
    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)


def _fake_llm_response(text: str = "How can I help you today?"):
    """Minimal Anthropic message stub — stop_reason=end_turn, no tool calls."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [text_block]
    resp.usage.output_tokens = 10
    return resp


def _make_tenant_ctx():
    import uuid
    from app.agent.agent import TenantContext
    return TenantContext(
        tenant_id=uuid.uuid4(),
        widget_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        tenant_name="Test Business",
        persona="a helpful and friendly assistant",
        allowed_topics="all business-related topics",
    )


# ── Eval test ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_tool_selection():
    """Run each golden-set message through the router with mocked dependencies.

    Prints per-class accuracy and a miss report.
    After the run, set agent_tool_selection.accuracy in eval_thresholds.yaml.
    """
    from app.agent.router import route
    from app.core.modelserver_client import ClassifyResult

    examples = _load_golden_set()
    thresholds = _load_thresholds()

    hits: list[bool] = []
    misses: list[dict] = []

    for ex in examples:
        message = ex["message"]
        # golden set stores null as YAML null; normalise to Python None
        expected = ex.get("expected_tool") or None
        label, confidence = _CLASSIFY_MAP[expected]

        mock_classify = AsyncMock(return_value=ClassifyResult(label=label, confidence=confidence))
        mock_llm     = AsyncMock(return_value=_fake_llm_response())
        mock_retrieve = AsyncMock(return_value=[])
        mock_escalate = AsyncMock(return_value="Conversation escalated to a human agent.")
        mock_lead     = AsyncMock(return_value="Lead captured successfully.")
        mock_rag      = AsyncMock(return_value="No relevant information found.")

        with (
            patch("app.agent.router.modelserver_client.classify", mock_classify),
            patch("app.core.llm.chat_completion",                 mock_llm),
            patch("app.agent.router.retrieve",                    mock_retrieve),
            patch("app.agent.tools.escalate.EscalateTool.__call__",   mock_escalate),
            patch("app.agent.tools.capture_lead.CaptureLeadTool.__call__", mock_lead),
            patch("app.agent.tools.rag_search.RagSearchTool.__call__",    mock_rag),
        ):
            result = await route(
                message=message,
                messages=[],
                tenant_ctx=_make_tenant_ctx(),
                session=MagicMock(),
            )

        got = result.tool_used  # str | None
        hit = got == expected
        hits.append(hit)
        if not hit:
            misses.append({"message": message, "expected": expected, "got": got})

    accuracy = sum(hits) / len(hits)

    # ── Per-class breakdown ───────────────────────────────────────────────────
    classes = ["rag_search", "capture_lead", "escalate", None]
    class_hits: dict = {c: [] for c in classes}
    for ex, hit in zip(examples, hits):
        cls = ex.get("expected_tool") or None
        class_hits[cls].append(hit)

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"  Examples : {len(examples)}")
    print(f"  Accuracy : {accuracy:.3f}  ({sum(hits)}/{len(hits)})")
    print(f"{'─' * 60}")
    print(f"  {'Class':<20} {'Hits':>10}")
    print(f"  {'─'*20} {'─'*10}")
    cls_labels = {None: "null"}
    for cls in classes:
        h = class_hits[cls]
        label = cls_labels.get(cls, cls)
        print(f"  {label:<20} {sum(h):>5}/{len(h)}")
    print(f"{'─' * 60}")

    if misses:
        print(f"\n  Misses ({len(misses)}):")
        for m in misses:
            print(f"    {m['message']!r}")
            print(f"      expected : {m['expected']!r}")
            print(f"      got      : {m['got']!r}")

    print(f"\n  → Update eval_thresholds.yaml: agent_tool_selection.accuracy = {accuracy:.3f}")

    # ── Gate ──────────────────────────────────────────────────────────────────
    saved = thresholds.get("agent_tool_selection", {}).get("accuracy", 0.0)
    if saved > 0.0:
        assert accuracy >= saved, (
            f"accuracy {accuracy:.3f} dropped below committed threshold {saved:.3f}"
        )
    else:
        print("\n  ⚠  eval_thresholds.yaml still has placeholder 0.0 — set it after this run.")

