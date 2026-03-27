"""run_eval.py — Run 50-question eval dataset."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from src.prompts.prompts_registry import get_best_prompt
from src.rag.chain import ask

logger = logging.getLogger(__name__)

# Exact refusal/guardrail responses that should count as non-relevant for
# in-scope RAG questions. Keep these narrow to avoid false negatives.
_HARD_REFUSAL_MARKERS = (
    "i cannot find this in the available trial data.",
    "i am specialised in clinical trial data only.",
    "consult your medical or regulatory team.",
)


def _is_hard_refusal(answer: str) -> bool:
    """Return True when the answer is a strict refusal/guardrail response."""
    answer_normalized = " ".join(answer.lower().split())
    return any(marker in answer_normalized for marker in _HARD_REFUSAL_MARKERS)


def load_and_run_eval() -> dict:
    """
    Load the eval dataset and run the evaluation.

    Returns:
        dict: Dictionary containing aggregate evaluation results.
    """
    eval_path = Path("eval_datasets/clinicalchat_eval.jsonl")

    if not eval_path.exists():
        logger.error("Eval dataset not found at %s", eval_path)
        return {
            "faithfulness": 0.00,
            "relevance": 0.00,
            "sql_accuracy": 0.00,
            "sample_count": 0,
        }

    queries = [
        json.loads(line)
        for line in eval_path.read_text().splitlines()
        if line.strip()
    ]

    prompt_version = get_best_prompt()

    # Per-question accumulators
    faithfulness_scores: list[float] = []
    relevance_scores: list[float] = []
    sql_correct = 0
    n_rag = 0
    n_sql = 0
    n_oot = 0

    for query in queries:
        question = query.get("question", "")
        category = str(query.get("category", "rag")).strip().lower()
        expected = query.get("expected_answer", "")

        logger.info("Query: %s", question)

        try:
            response = ask(question=question, prompt_version=prompt_version)
        except Exception as exc:
            logger.error("ask() failed for question '%s': %s", question, exc)
            if category == "sql":
                n_sql += 1

            else:
                # Count failed in-scope RAG runs as 0s so quality regressions remain visible.
                n_rag += 1
                faithfulness_scores.append(0.0)
                relevance_scores.append(0.0)
            time.sleep(1.5)
            continue

        logger.info("Response: %s", response)

        if category == "sql":
            n_sql += 1
            if expected and expected.lower() in response.answer.lower():
                sql_correct += 1

        else:
            n_rag += 1

            cited_ncts = [s["nct_id"] for s in response.sources if s.get("nct_id")]
            answer_lower = response.answer.lower()
            grounded = any(nct.lower() in answer_lower for nct in cited_ncts)

            if _is_hard_refusal(response.answer):
                # Safe abstention is faithful (no hallucination), but not relevant
                # to an in-scope answer expectation.
                faithfulness_scores.append(1.0)
                relevance_scores.append(0.0)
            else:
                faithfulness_scores.append(1.0 if grounded else 0.0)
                relevance_scores.append(1.0 if response.answer.strip() else 0.0)

        time.sleep(1.5)  # prevent Bedrock throttling

    sample_count = n_rag + n_sql + n_oot

    scores = {
        "faithfulness": (
            sum(faithfulness_scores) / len(faithfulness_scores)
            if faithfulness_scores else 0.0
        ),
        "relevance": (
            sum(relevance_scores) / len(relevance_scores)
            if relevance_scores else 0.0
        ),
        "sql_accuracy": (sql_correct / n_sql) if n_sql else 0.0,
        "sample_count": sample_count,
        "rag_sample_count": n_rag,
        "sql_sample_count": n_sql,
        "oot_sample_count": n_oot,
    }

    logger.info("Eval aggregate scores: %s", scores)
    return scores
