from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from statistics import mean

from src.evaluation.scorers import (
    score_faithfulness,
    score_answer_relevance,
    score_citation_presence,
)
from src.prompts.prompts_registry import get_best_prompt
from src.rag.chain import ask

logger = logging.getLogger(__name__)

EVAL_DATASET_PATH = Path("eval_datasets/clinicalchat_eval.jsonl")

# Rate-limit guard between Bedrock calls (scorer + chain = multiple calls per sample)
SLEEP_BETWEEN_SAMPLES: float = 2.0

# Refusal phrases the chain emits when it has no answer.
# These are faithful (no hallucination) but irrelevant to the eval question.
_HARD_REFUSAL_MARKERS = (
    "i cannot find this in the available trial data.",
    "i am specialised in clinical trial data only.",
    "consult your medical or regulatory team.",
)


def _is_hard_refusal(answer: str) -> bool:
    """True when the answer is a guardrail refusal rather than a real response."""
    normalised = " ".join(answer.lower().split())
    return any(marker in normalised for marker in _HARD_REFUSAL_MARKERS)


def _keyword_hit(answer: str, expected_keywords: list[str]) -> float:
    """
    Rule-based check: fraction of expected_keywords found in the answer.

    Examples:
        keywords=["recruiting", "diabetes"], answer contains both → 1.0
        keywords=["recruiting", "diabetes"], answer contains one  → 0.5
        keywords=[]                                               → 1.0 (vacuously true)
    """
    if not expected_keywords:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return hits / len(expected_keywords)


def _load_dataset() -> list[dict]:
    """Load and parse the JSONL eval dataset. Returns [] on missing/corrupt file."""
    if not EVAL_DATASET_PATH.exists():
        logger.error("Eval dataset not found at %s", EVAL_DATASET_PATH)
        return []

    queries = []
    for i, line in enumerate(EVAL_DATASET_PATH.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            queries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed line %d in dataset: %s", i, exc)

    logger.info("Loaded %d eval samples from %s", len(queries), EVAL_DATASET_PATH)
    return queries


def load_and_run_eval() -> dict:
    """
    Run every question in the eval dataset through the production RAG chain
    and score each response with scorers.py + rule-based checks.

    Scoring per sample
    ------------------
    faithfulness  : score_faithfulness(context, answer)       — LLM-as-judge
    relevance     : score_answer_relevance(question, answer)  — LLM-as-judge
    citation      : score_citation_presence(answer, sources)  — NCT ID match
    keyword_hit   : all expected_keywords in answer           — string match

    Hard refusals (guardrail responses) are treated as:
        faithfulness = 1.0  (no hallucination)
        relevance    = 0.0  (did not answer the question)
        citation     = 0.0  (no NCT IDs cited)
        keyword_hit  = 0.0  (keywords not in refusal text)

    Returns
    -------
    dict with keys:
        faithfulness, relevance, citation_presence (citation proxy),
        keyword_coverage, sample_count, failed_count
    """
    queries = _load_dataset()

    if not queries:
        return {
            "faithfulness":      0.0,
            "relevance":         0.0,
            "citation_presence": 0.0,
            "keyword_coverage":  0.0,
            "sample_count":      0,
            "failed_count":      0,
        }

    prompt_version = get_best_prompt()
    logger.info("Running eval with prompt version: %s", prompt_version)

    # ── Per-sample accumulators ────────────────────────────────────────────
    faithfulness_scores: list[float] = []
    relevance_scores:    list[float] = []
    citation_scores:     list[float] = []
    keyword_scores:      list[float] = []
    failed_count = 0

    for i, sample in enumerate(queries, start=1):
        question          = sample.get("question", "").strip()
        expected_keywords = sample.get("expected_keywords", [])

        if not question:
            logger.warning("Sample %d has no question field — skipping.", i)
            continue

        logger.info("── Sample %d/%d: %s", i, len(queries), question)

        # ── Step 1: Run the production RAG chain ───────────────────────────
        try:
            response = ask(question=question, prompt_version=prompt_version)
        except Exception as exc:
            logger.error("ask() failed for sample %d ('%s'): %s", i, question, exc)
            # Count as failed — append 0s so regressions remain visible
            faithfulness_scores.append(0.0)
            relevance_scores.append(0.0)
            citation_scores.append(0.0)
            keyword_scores.append(0.0)
            failed_count += 1
            time.sleep(SLEEP_BETWEEN_SAMPLES)
            continue

        answer  = response.answer
        sources = response.sources           # list[dict] with "nct_id" key
        context = response.context           # full retrieved context text

        logger.info("Answer preview: %.120s", answer)

        # ── Step 2: Hard refusal shortcut ─────────────────────────────────
        if _is_hard_refusal(answer):
            logger.info("Sample %d → hard refusal detected.", i)
            faithfulness_scores.append(1.0)  # no hallucination in a refusal
            relevance_scores.append(0.0)     # did not answer the question
            citation_scores.append(0.0)      # no NCT IDs cited
            keyword_scores.append(0.0)       # keywords not in refusal text
            time.sleep(SLEEP_BETWEEN_SAMPLES)
            continue

        # ── Step 3: Score with scorers.py ──────────────────────────────────
        try:
            f_score = score_faithfulness(
                context=context,
                answer=answer,
            )
        except Exception as exc:
            logger.error("score_faithfulness failed for sample %d: %s", i, exc)
            f_score = 0.5   # neutral fallback, same as scorer's own fallback

        try:
            r_score = score_answer_relevance(
                question=question,
                answer=answer,
            )
        except Exception as exc:
            logger.error("score_answer_relevance failed for sample %d: %s", i, exc)
            r_score = 0.5

        c_score = score_citation_presence(answer=answer, sources=sources)
        k_score = _keyword_hit(answer=answer, expected_keywords=expected_keywords)

        faithfulness_scores.append(f_score)
        relevance_scores.append(r_score)
        citation_scores.append(c_score)
        keyword_scores.append(k_score)

        logger.info(
            "Sample %d scores — faithfulness: %.3f | relevance: %.3f "
            "| citation: %.3f | keywords: %.3f",
            i, f_score, r_score, c_score, k_score,
        )

        # Rate-limit: chain + 2 LLM scorer calls per sample
        time.sleep(SLEEP_BETWEEN_SAMPLES)

    # ── Aggregate ──────────────────────────────────────────────────────────
    sample_count = len(faithfulness_scores)

    if sample_count == 0:
        raise RuntimeError(
            "All eval samples failed — check the RAG chain and DB connection."
        )

    scores = {
        "faithfulness": round(mean(faithfulness_scores), 4),
        "relevance": round(mean(relevance_scores), 4),
        "citation_presence": round(mean(citation_scores), 4),
        "keyword_coverage": round(mean(keyword_scores), 4),
        "sample_count": sample_count,
        "failed_count": failed_count,
    }

    logger.info("── Eval complete. Aggregate scores: %s", scores)
    return scores