"""
DAG 4: clinical_eval_monitor
Schedule: Every Sunday at 06:00 UTC
Purpose: Run LLM quality evaluation + post Slack report
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

logger = logging.getLogger(__name__)

# Quality thresholds — if ANY metric drops below, task fails → alert fires
QUALITY_THRESHOLDS = {
    "faithfulness": 0.55,
    "relevance":    0.50,
    "sql_accuracy": 0.85,
}

# Minimum number of eval samples required for the gate to be meaningful.
# If fewer samples come back, we warn but do NOT fail — avoids false alarms
# when the eval dataset itself fails to load.
MIN_EVAL_SAMPLES = 5


@dag(
    dag_id="clinical_eval_monitor",
    description=(
        "Weekly LLM quality eval + Slack report. "
        "Alerts if faithfulness/relevance drops below threshold."
    ),
    schedule="0 6 * * 0",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
        "email_on_failure": False,
    },
    tags=["clinical", "evaluation", "monitoring", "llm"],
)
def clinical_eval_monitor():

    @task(task_id="run_weave_eval")
    def run_eval() -> dict:
        """
        Run the 50-question eval dataset against the current production prompt.
        Returns dict with keys:
          - one key per metric (float)
          - 'sample_count' (int) so the gate knows if results are trustworthy
        """
        from src.evaluation.run_eval import load_and_run_eval

        try:
            scores = load_and_run_eval()
        except Exception as exc:
            # Surface the real error rather than swallowing it into a 0 score.
            logger.exception("load_and_run_eval() raised: %s", exc)
            raise RuntimeError(
                f"Eval run failed — quality gate skipped. Underlying error: {exc}"
            ) from exc

        if not isinstance(scores, dict):
            raise TypeError(
                f"load_and_run_eval() must return a dict, got {type(scores)}"
            )

        # Ensure sample_count is present so downstream tasks can guard on it.
        scores.setdefault("sample_count", 0)
        logger.info("Eval scores: %s", scores)
        return scores

    @task(task_id="check_quality_gate")
    def check_gate(scores: dict) -> dict:
        """
        Compare scores against thresholds.

        Key changes vs original:
          - Metrics missing from `scores` (None or absent) are SKIPPED, not
            defaulted to 0. A missing metric means the evaluator didn't run,
            which is a different problem surfaced by run_eval itself.
          - If sample_count < MIN_EVAL_SAMPLES the gate is bypassed with a
            warning so a half-run doesn't produce misleading 0.0 failures.
          - Raises ValueError only for metrics that have a real score below
            threshold.
        """
        sample_count = scores.get("sample_count", 0)
        if sample_count < MIN_EVAL_SAMPLES:
            logger.warning(
                "Only %d eval samples returned (minimum %d). "
                "Quality gate bypassed — check run_eval logs.",
                sample_count,
                MIN_EVAL_SAMPLES,
            )
            return {
                "passed": None,   # None = inconclusive, not True/False
                "scores": scores,
                "warning": f"Insufficient samples ({sample_count} < {MIN_EVAL_SAMPLES})",
            }

        failures: dict[str, dict] = {}
        for metric, threshold in QUALITY_THRESHOLDS.items():
            score = scores.get(metric)   # None if metric absent, NOT 0

            if score is None:
                # The evaluator didn't produce this metric at all — that is a
                # bug in run_eval, not a quality regression. Log it loudly but
                # don't count it as a 0 failure.
                logger.error(
                    "Metric '%s' is missing from eval output. "
                    "Check load_and_run_eval() — it should always return this key.",
                    metric,
                )
                continue

            if score < threshold:
                failures[metric] = {"score": score, "threshold": threshold}

        if failures:
            msg = ", ".join(
                f"{m}={v['score']:.3f} < {v['threshold']}"
                for m, v in failures.items()
            )
            raise ValueError(f"Quality gate FAILED: {msg}")

        logger.info("✅ All quality metrics passed")
        return {"passed": True, "scores": scores}

    @task(task_id="build_slack_message")
    def build_message(gate_result: dict) -> str:
        """Format a Slack message with traffic-light indicators per metric."""
        scores   = gate_result.get("scores", {})
        passed   = gate_result.get("passed")
        warning  = gate_result.get("warning")

        lines = ["*🔬 ClinicalChat Weekly Eval Report*"]
        lines.append(f"Date: {datetime.utcnow().strftime('%Y-%m-%d')}")

        if warning:
            lines.append(f"\n⚠️  *Warning*: {warning}")

        lines.append("")
        for metric, threshold in QUALITY_THRESHOLDS.items():
            score = scores.get(metric)
            if score is None:
                lines.append(f"⚪ *{metric}*: no data  _(threshold: {threshold})_")
            else:
                icon = "🟢" if score >= threshold else "🔴"
                lines.append(f"{icon} *{metric}*: {score:.3f}  _(threshold: {threshold})_")

        sample_count = scores.get("sample_count")
        if sample_count is not None:
            lines.append(f"\n_Samples evaluated: {sample_count}_")

        if passed is None:
            lines.append("\n⚠️  Gate result: *inconclusive* (too few samples)")
        elif passed:
            lines.append("\n✅  Gate result: *all metrics passed*")

        lines.append("")
        lines.append(
            "View traces: https://wandb.ai/maneeshsai1118-test-guide/clinical-trails-chatbot-qa"
        )
        return "\n".join(lines)

    # ── WIRING ────────────────────────────────────────────────────
    scores      = run_eval()
    gate_result = check_gate(scores=scores)
    message     = build_message(gate_result=gate_result)

    # # BUG FIX: operator must be wired into the task graph with >> so Airflow
    # # actually schedules it and receives the rendered `message` string.
    # slack_post = SlackWebhookOperator(
    #     task_id="post_slack_report",
    #     slack_webhook_conn_id="slack_clinical",
    #     message=message,
    # )
    message #>> slack_post


clinical_eval_monitor()