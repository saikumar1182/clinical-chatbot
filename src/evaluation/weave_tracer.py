"""
weave_tracer.py — Weave tracing integration.

Key design decisions:
  - log_llm_traces is a @weave.op so the function call itself becomes the
    remote trace (inputs, outputs, timing, parent-child nesting).
    weave.publish() is for datasets/models — NOT for logging traces.
  - If weave.init() fails (network issue, bad API key, gql conflict),
    the function still runs normally and logs locally. Weave is optional.
  - We apply a small gql compatibility shim before importing weave because
    weave==0.52.35 references TransportConnectionFailed, which is absent in
    current stable gql releases.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import text
from src.db.connection import engine

logger = logging.getLogger(__name__)

_WEAVE_READY = False


def _patch_gql_exceptions_for_weave() -> None:
    """
    Add a compatibility alias expected by weave 0.52.x.

    weave imports `TransportConnectionFailed` from gql, but stable gql
    exposes `TransportServerError` instead. A runtime alias keeps Weave
    initialization functional without forking vendor packages.
    """
    try:
        from gql.transport import exceptions as gql_exceptions
    except Exception:
        return

    if hasattr(gql_exceptions, "TransportConnectionFailed"):
        return

    class TransportConnectionFailed(gql_exceptions.TransportServerError):
        pass

    gql_exceptions.TransportConnectionFailed = TransportConnectionFailed


def _init_weave() -> bool:
    """
    Initialize Weave once per process. Safe to call many times.
    Uses WANDB_API_KEY from env for automatic auth.
    Uses WEAVE_PROJECT env var for the project name.
    Suppresses call-link noise via env var rather than the settings dict
    (which has inconsistent support across weave patch versions).
    """
    global _WEAVE_READY
    if _WEAVE_READY:
        return True

    # Suppress the per-call "View trace at: https://..." log lines
    os.environ.setdefault("WEAVE_PRINT_CALL_LINK", "false")

    try:
        _patch_gql_exceptions_for_weave()
        import weave
        weave.init(os.getenv("WEAVE_PROJECT", "clinical-trials-chatbot-qa"))
        _WEAVE_READY = True
        logger.info("Weave initialized successfully")
        return True
    except Exception as exc:
        logger.warning("Weave init failed: %s", exc)
        return False


def log_llm_traces(
    *,
    trace_id: str,
    question: str,
    answer: str,
    sources: list[dict],
    prompt_version: str,
    latency_ms: int,
    context: str,
    query_type: str | None = None,
    sql_query: str | None = None,
) -> dict[str, Any]:
    """
    Persist one trace row to eval.traces (always runs).
    If Weave is available, also records a remote Weave trace via @weave.op.

    NOTE: weave.publish() is intentionally NOT used here — it is the API
    for uploading datasets and model objects, not for logging call traces.
    The @weave.op decorator on _weave_log_trace() is the correct mechanism.
    """
    nct_ids = [s["nct_id"] for s in sources if s.get("nct_id")]

    # ── 1. Always write locally ───────────────────────────────────────────────
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO eval.traces (
                    trace_id,
                    question,
                    answer,
                    query_type,
                    retrieved_ncts,
                    prompt_version,
                    latency_ms
                ) VALUES (
                    :trace_id,
                    :question,
                    :answer,
                    :query_type,
                    :retrieved_ncts,
                    :prompt_version,
                    :latency_ms
                )
            """),
            {
                "trace_id":      trace_id,
                "question":      question,
                "answer":        answer,
                "query_type":    query_type,
                "retrieved_ncts": nct_ids,
                "prompt_version": prompt_version,
                "latency_ms":    latency_ms,
            },
        )
    logger.info("Local trace logged successfully: %s", trace_id)

    # ── 2. Optionally push to Weave ───────────────────────────────────────────
    if _init_weave():
        try:
            _weave_log_trace(
                trace_id=trace_id,
                question=question,
                answer=answer,
                query_type=query_type,
                nct_ids=nct_ids,
                prompt_version=prompt_version,
                latency_ms=latency_ms,
                context=context,
                sql_query=sql_query,
                source_count=len(sources),
            )
        except Exception as exc:
            logger.warning("Weave trace failed: %s", exc)

    return {
        "trace_id":     trace_id,
        "latency_ms":   latency_ms,
        "source_count": len(sources),
    }


def _weave_log_trace(**kwargs: Any) -> dict[str, Any]:
    """
    Inner function decorated with @weave.op at import time (if Weave loaded).
    Defined separately so the decorator is applied only once, and the rest of
    the module works fine if weave is not installed.

    Returns the kwargs dict so Weave captures both inputs and outputs.
    """
    return kwargs


# Apply @weave.op only if weave is importable — keeps the module importable
# even in environments where weave is not installed.
try:
    _patch_gql_exceptions_for_weave()
    import weave as _weave
    _weave_log_trace = _weave.op(name="clinical_llm_trace")(_weave_log_trace)
except Exception:
    pass  # Weave unavailable — _weave_log_trace stays as a plain function
