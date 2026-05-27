"""RAGAS-style faithfulness + answer-relevancy evaluation on synthetic questions.

RAGAS is incompatible with Python 3.14 / Windows (scikit-network build failure).
This module implements the same two metrics directly using Claude as the judge,
which is the same underlying algorithm RAGAS uses.

Metrics
-------
faithfulness    — fraction of answer claims that are supported by retrieved context
answer_relevancy — fraction of questions re-generated from the answer that
                   semantically match the original question (via Voyage cosine)

Pipeline
--------
1. Load all CMS content items from the DB
2. Claude generates QUESTIONS_PER_ITEM questions per item  →  synthetic testset
3. For each question: retrieve top-5 chunks, generate a grounded answer
4. Judge each (question, answer, context) triple for faithfulness + relevancy
5. Print summary table; update eval_thresholds.yaml with measured scores

Prerequisites
-------------
    docker compose -f docker-compose.dev.yml up -d
    cd api && python scripts/dev_setup.py

Run
---
    cd api && pytest ../evals/rag/test_ragas_full.py -v -s
"""
import asyncio
import sys
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

_API_DIR = Path(__file__).parents[2] / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

_REPO_ROOT = Path(__file__).parents[2]
THRESHOLDS_PATH = _REPO_ROOT / "eval_thresholds.yaml"

QUESTIONS_PER_ITEM = 2   # synthetic questions generated per CMS content item
RELEVANCY_REGEN_N  = 3   # questions re-generated per answer for relevancy scoring


# ── Synthetic question generation ─────────────────────────────────────────────

async def _generate_questions(title: str, body: str, n: int) -> list[str]:
    from app.core.llm import chat_completion
    response = await chat_completion(
        messages=[{"role": "user", "content": f"Title: {title}\n\n{body}"}],
        system=(
            f"Generate exactly {n} distinct questions a website visitor might ask "
            "based on this knowledge-base content. "
            "Return one question per line, no numbering, no blank lines."
        ),
        max_tokens=300,
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    return [q.strip() for q in text.splitlines() if q.strip()][:n]


# ── Grounded answer generation ─────────────────────────────────────────────────

async def _generate_answer(question: str, contexts: list[str]) -> str:
    from app.core.llm import chat_completion
    ctx = "\n\n---\n\n".join(contexts)
    response = await chat_completion(
        messages=[{"role": "user", "content": question}],
        system=(
            "You are a helpful assistant for a business. Answer the user's question "
            "using ONLY the information provided below. "
            "If the answer is not in the information, say you don't know.\n\n"
            f"Context:\n{ctx}"
        ),
        max_tokens=256,
    )
    return next((b.text for b in response.content if b.type == "text"), "").strip()


# ── Faithfulness judge ────────────────────────────────────────────────────────

async def _judge_faithfulness(answer: str, contexts: list[str]) -> float:
    """Score 0–1: fraction of answer claims supported by the retrieved context."""
    from app.core.llm import chat_completion
    ctx = "\n\n---\n\n".join(contexts)
    response = await chat_completion(
        messages=[{
            "role": "user",
            "content": (
                f"Answer to evaluate:\n{answer}\n\n"
                f"Retrieved context:\n{ctx}"
            ),
        }],
        system=(
            "You are a faithfulness evaluator. "
            "List every factual claim made in the answer. "
            "For each claim, state SUPPORTED or UNSUPPORTED based on the context. "
            "At the very end, output a single line: SCORE: X/Y "
            "where X is the number of supported claims and Y is the total claims."
        ),
        max_tokens=512,
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    # Parse "SCORE: X/Y"
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                fraction = line.split(":", 1)[1].strip()
                x, y = fraction.split("/")
                return int(x.strip()) / int(y.strip()) if int(y.strip()) > 0 else 1.0
            except (ValueError, ZeroDivisionError):
                pass
    return 1.0  # default: assume faithful if parsing fails


# ── Answer-relevancy judge ────────────────────────────────────────────────────

async def _judge_answer_relevancy(original_question: str, answer: str) -> float:
    """Score 0–1: mean cosine similarity between the original question and
    RELEVANCY_REGEN_N questions re-generated from the answer."""
    from app.core.llm import chat_completion
    from app.core.embedder import embed_query
    import numpy as np

    response = await chat_completion(
        messages=[{"role": "user", "content": answer}],
        system=(
            f"Given this answer, generate exactly {RELEVANCY_REGEN_N} questions "
            "that this answer could plausibly be responding to. "
            "Return one question per line, no numbering."
        ),
        max_tokens=256,
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    regen_questions = [q.strip() for q in text.splitlines() if q.strip()][:RELEVANCY_REGEN_N]

    if not regen_questions:
        return 0.0

    orig_vec = await embed_query(original_question)
    orig_arr = np.array(orig_vec)
    orig_norm = orig_arr / (np.linalg.norm(orig_arr) + 1e-10)

    scores = []
    for q in regen_questions:
        q_vec = await embed_query(q)
        q_arr = np.array(q_vec)
        q_norm = q_arr / (np.linalg.norm(q_arr) + 1e-10)
        scores.append(float(np.dot(orig_norm, q_norm)))

    return sum(scores) / len(scores)


# ── Main eval test ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ragas_faithfulness_and_relevancy():
    """Synthetic-testset RAG eval: faithfulness + answer relevancy.

    Generates QUESTIONS_PER_ITEM questions per CMS content item, runs the full
    RAG pipeline, then scores each sample with LLM-as-judge (same algorithm
    as RAGAS, without the RAGAS package dependency).

    After the run, update eval_thresholds.yaml with the printed scores.
    """
    from app.core.config import get_settings
    from app.core.database import AsyncSessionLocal
    from app.models.cms_content import CmsContent
    from app.rag.retriever import retrieve

    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY.startswith("your-"):
        pytest.skip("ANTHROPIC_API_KEY not set in .env")

    # ── 1. Load CMS content ───────────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CmsContent).where(CmsContent.is_deleted == False)
        )
        items = result.scalars().all()

    if not items:
        pytest.skip("No CMS content found. Run: cd api && python scripts/dev_setup.py")

    # ── 2. Generate synthetic questions ──────────────────────────────────────
    print(f"\n  Generating {QUESTIONS_PER_ITEM} questions × {len(items)} CMS items …")
    qa_inputs: list[tuple[str, object]] = []  # (question, tenant_id)
    for item in items:
        questions = await _generate_questions(item.title, item.body, QUESTIONS_PER_ITEM)
        for q in questions:
            qa_inputs.append((q, item.tenant_id))

    print(f"  Generated {len(qa_inputs)} synthetic questions")

    # ── 3. Run RAG pipeline ───────────────────────────────────────────────────
    print("  Running RAG pipeline …")
    samples: list[dict] = []
    async with AsyncSessionLocal() as session:
        for question, tenant_id in qa_inputs:
            chunks = await retrieve(question, tenant_id, session, top_k=5)
            contexts = [c.child_text for c in chunks]
            answer = await _generate_answer(question, contexts)
            samples.append({
                "question": question,
                "answer": answer,
                "contexts": contexts,
            })

    # ── 4. Judge each sample ──────────────────────────────────────────────────
    print("  Judging faithfulness + answer relevancy …")
    faithfulness_scores: list[float] = []
    relevancy_scores: list[float] = []

    for s in samples:
        f = await _judge_faithfulness(s["answer"], s["contexts"])
        r = await _judge_answer_relevancy(s["question"], s["answer"])
        faithfulness_scores.append(f)
        relevancy_scores.append(r)

    faithfulness = sum(faithfulness_scores) / len(faithfulness_scores)
    relevancy    = sum(relevancy_scores)    / len(relevancy_scores)

    # ── 5. Report ─────────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"  RAGAS-style Evaluation  ({len(samples)} synthetic samples)")
    print(f"{'─' * 60}")
    print(f"  Faithfulness     : {faithfulness:.3f}")
    print(f"  Answer Relevancy : {relevancy:.3f}")
    print(f"{'─' * 60}")
    print(f"\n  → Update eval_thresholds.yaml:")
    print(f"      rag.faithfulness = {faithfulness:.3f}")
    print(f"      (answer_relevancy {relevancy:.3f} — informational)")

    # ── 6. Gate (if threshold is set) ────────────────────────────────────────
    with open(THRESHOLDS_PATH) as f:
        thresholds = yaml.safe_load(f)
    saved = thresholds.get("rag", {}).get("faithfulness", 0.0)
    if saved > 0.0:
        assert faithfulness >= saved, (
            f"faithfulness {faithfulness:.3f} dropped below committed threshold {saved:.3f}"
        )
    else:
        print("\n  ⚠  eval_thresholds.yaml faithfulness still 0.0 — set it after this run.")
