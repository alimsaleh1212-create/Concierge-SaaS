"""RAG retrieval eval — hit@5 and MRR against the 15-triple golden set.

test_rag_hit_at_5_and_mrr  — gates on eval_thresholds.yaml; Voyage only (no Anthropic key needed)
test_rag_strategy_comparison — compares baseline / reranking / query_rewrite / HyDE side-by-side
                                (LLM strategies skipped if ANTHROPIC_API_KEY not set)

Prerequisites:
    docker compose -f docker-compose.dev.yml up -d
    cd api && python scripts/dev_setup.py   # creates tables, seeds, embeds content

Run from the api/ directory so pyproject.toml (asyncio_mode=auto) is picked up:
    cd api && pytest ../evals/rag/test_rag.py -v -s
    cd api && pytest ../evals/rag/test_rag.py::test_rag_strategy_comparison -v -s

After the gate run, update eval_thresholds.yaml manually with the printed hit@5 value (T-B038).
After the comparison run, update DECISIONS.md RAG-001 table with measured numbers.
"""
import sys
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

# Make api/app importable when running from api/
_API_DIR = Path(__file__).parents[2] / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

_HERE = Path(__file__).parent
_REPO_ROOT = Path(__file__).parents[2]

GOLDEN_SET_PATH = _HERE / "golden_set.yaml"
THRESHOLDS_PATH = _REPO_ROOT / "eval_thresholds.yaml"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_golden_set() -> list[dict]:
    with open(GOLDEN_SET_PATH) as f:
        return yaml.safe_load(f)["triples"]


def _load_thresholds() -> dict:
    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)


def _matches(gt_chunk: str, child_text: str, parent_text: str) -> bool:
    """Ground truth chunk must appear in retrieved child or parent text."""
    gt = gt_chunk.strip()
    return gt in child_text or gt in parent_text


def _is_hit(ground_truth_chunks: list[str], results) -> bool:
    return any(
        _matches(gt, r.child_text, r.parent_text)
        for r in results
        for gt in ground_truth_chunks
    )


def _reciprocal_rank(ground_truth_chunks: list[str], results) -> float:
    for rank, r in enumerate(results, start=1):
        if any(_matches(gt, r.child_text, r.parent_text) for gt in ground_truth_chunks):
            return 1.0 / rank
    return 0.0


# ── Eval test ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rag_hit_at_5_and_mrr():
    """Retrieve top-5 chunks for each golden-set triple; compute hit@5 and MRR.

    Skips all triples if the tenants are not yet seeded.
    Prints a miss report so you can see exactly which questions fail.
    After the run, copy the printed hit@5 into eval_thresholds.yaml (T-B038).
    """
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Tenant
    from app.rag.retriever import retrieve

    triples = _load_golden_set()
    thresholds = _load_thresholds()

    # Build slug → UUID map from the live database
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Tenant))
        tenant_map = {t.slug: t.id for t in result.scalars().all()}

    missing = {t["tenant"] for t in triples} - tenant_map.keys()
    if missing:
        pytest.skip(
            f"Tenants not seeded: {missing}. Run: cd api && python scripts/dev_setup.py"
        )

    hits: list[bool] = []
    rr_scores: list[float] = []
    misses: list[dict] = []

    async with AsyncSessionLocal() as session:
        for triple in triples:
            results = await retrieve(
                triple["question"], tenant_map[triple["tenant"]], session, top_k=5
            )
            hit = _is_hit(triple["ground_truth_chunks"], results)
            rr = _reciprocal_rank(triple["ground_truth_chunks"], results)
            hits.append(hit)
            rr_scores.append(rr)
            if not hit:
                misses.append({
                    "tenant": triple["tenant"],
                    "question": triple["question"],
                    "expected": triple["ground_truth_chunks"],
                    "got": [r.child_text for r in results],
                })

    hit_at_5 = sum(hits) / len(hits)
    mrr = sum(rr_scores) / len(rr_scores)

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"  Triples : {len(triples)}")
    print(f"  Hit@5   : {hit_at_5:.3f}  ({sum(hits)}/{len(hits)})")
    print(f"  MRR     : {mrr:.3f}")
    print(f"{'─' * 60}")

    if misses:
        print(f"\n  Misses ({len(misses)}):")
        for m in misses:
            print(f"    [{m['tenant']}] {m['question']!r}")
            for gt in m["expected"]:
                print(f"      expected : {gt!r}")
            for got in m["got"]:
                print(f"      got      : {got!r}")

    print(f"\n  → Update eval_thresholds.yaml: rag.hit_at_5 = {hit_at_5:.3f}")
    print(f"  → MRR (informational):         {mrr:.3f}")

    # ── Gate ──────────────────────────────────────────────────────────────────
    saved = thresholds.get("rag", {}).get("hit_at_5", 0.0)
    if saved > 0.0:
        assert hit_at_5 >= saved, (
            f"hit@5 {hit_at_5:.3f} dropped below committed threshold {saved:.3f}"
        )
    else:
        # Thresholds not set yet — pass and remind the user to update
        print("\n  ⚠  eval_thresholds.yaml still has placeholder 0.0 — set it after this run.")


# ── Strategy comparison (informational — no threshold gate) ───────────────────

@pytest.mark.asyncio
async def test_rag_strategy_comparison():
    """Compare baseline / reranking / query_rewrite / HyDE on the 15-triple golden set.

    LLM-based strategies (hyde, query_rewrite) are skipped if ANTHROPIC_API_KEY is not set.
    This test never gates — run it to fill in the DECISIONS.md RAG-001 table.

    Run:
        cd api && pytest ../evals/rag/test_rag.py::test_rag_strategy_comparison -v -s
    """
    from app.core.config import get_settings
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Tenant
    from app.rag.retriever import (
        _retrieve_baseline,
        _retrieve_with_hyde,
        _retrieve_with_query_rewrite,
        _retrieve_with_rerank,
    )

    triples = _load_golden_set()
    settings = get_settings()
    has_anthropic = bool(
        settings.ANTHROPIC_API_KEY
        and not settings.ANTHROPIC_API_KEY.startswith("your-")
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Tenant))
        tenant_map = {t.slug: t.id for t in result.scalars().all()}

    missing = {t["tenant"] for t in triples} - tenant_map.keys()
    if missing:
        pytest.skip(
            f"Tenants not seeded: {missing}. Run: cd api && python scripts/dev_setup.py"
        )

    strategies: dict = {"baseline": _retrieve_baseline, "reranking": _retrieve_with_rerank}
    if has_anthropic:
        strategies["query_rewrite"] = _retrieve_with_query_rewrite
        strategies["hyde"] = _retrieve_with_hyde
    else:
        print("\n  ANTHROPIC_API_KEY not set — skipping query_rewrite and hyde")

    table: dict[str, dict] = {}
    async with AsyncSessionLocal() as session:
        for name, fn in strategies.items():
            hits: list[bool] = []
            rr_scores: list[float] = []
            for triple in triples:
                results = await fn(
                    triple["question"], tenant_map[triple["tenant"]], session, top_k=5
                )
                hits.append(_is_hit(triple["ground_truth_chunks"], results))
                rr_scores.append(_reciprocal_rank(triple["ground_truth_chunks"], results))
            table[name] = {
                "hit_at_5": sum(hits) / len(hits),
                "mrr": sum(rr_scores) / len(rr_scores),
                "hits": sum(hits),
            }

    print(f"\n{'─' * 60}")
    print(f"  Strategy Comparison  ({len(triples)} triples)")
    print(f"{'─' * 60}")
    print(f"  {'Strategy':<20} {'Hit@5':>8} {'MRR':>8} {'Hits':>8}")
    print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*8}")
    for name, r in sorted(table.items(), key=lambda x: -x[1]["hit_at_5"]):
        marker = " ← active" if name == "reranking" else ""
        print(
            f"  {name:<20} {r['hit_at_5']:>8.3f} {r['mrr']:>8.3f}"
            f" {r['hits']:>5}/{len(triples)}{marker}"
        )
    print(f"{'─' * 60}")
    print("\n  → Update DECISIONS.md RAG-001 table with these numbers.")
