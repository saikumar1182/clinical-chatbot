"""
DAG 4: clinical_eval_monitor
Schedule: Every Sunday at 06:00 UTC
Purpose: Run LLM quality evaluation + post Slack report

Completely new — had no equivalent in run_ingestion.py.
Runs the 50-question eval dataset weekly, checks quality thresholds,
and posts a traffic-light report to Slack.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

logger = logging.getLogger(__name__)

# Quality thresholds — if ANY metric drops below, task fails → alert fires
QUALITY_THRESHOLDS = {
    "faithfulness": 0.75,   # Fraction of answers grounded in retrieved context
    "relevance":    0.70,   # Fraction of answers that address the question
    "sql_accuracy": 0.88,   # Fraction of SQL queries that return correct results
}


@dag(
    dag_id="clinical_eval_monitor",
    description=(
        "Weekly LLM quality eval + Slack report. "
        "Alerts if faithfulness/relevance drops below threshold."
    ),
    schedule="0 6 * * 0",              # Every Sunday at 06:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
        "email_on_failure": True,
        "email": ["data-alerts@clinicalchat.local"],
    },
    tags=["clinical", "evaluation", "monitoring", "llm"],
)
def clinical_eval_monitor():

    @task(task_id="run_weave_eval")
    def run_eval() -> dict:
        """
        Run the 50-question eval dataset against the current production prompt.
        Returns dict of metric_name → score.
        Logged to Weave for trend visualisation.
        """
        from src.evaluation.run_eval import run_full_eval
        scores = run_full_eval()
        logger.info(f"Eval scores: {scores}")
        return scores

    @task(task_id="check_quality_gate")
    def check_gate(scores: dict) -> dict:
        """
        Compare scores against thresholds.
        Raises ValueError if any metric is below threshold —
        Airflow marks this task FAILED and sends email alert.
        """
        failures = {
            metric: {"score": scores.get(metric, 0), "threshold": threshold}
            for metric, threshold in QUALITY_THRESHOLDS.items()
            if scores.get(metric, 0) < threshold
        }

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
        scores = gate_result["scores"]
        lines = ["*🔬 ClinicalChat Weekly Eval Report*"]
        lines.append(f"Date: {datetime.utcnow().strftime('%Y-%m-%d')}")
        lines.append("")
        for metric, score in scores.items():
            threshold = QUALITY_THRESHOLDS.get(metric, 0)
            icon = "🟢" if score >= threshold else "🔴"
            lines.append(
                f"{icon} *{metric}*: {score:.3f}  _(threshold: {threshold})_"
            )
        lines.append("")
        lines.append("View traces: https://wandb.ai/your-project/clinicalchat-qa")
        return "\n".join(lines)

    # ── WIRING ────────────────────────────────────────────────────
    scores      = run_eval()
    gate_result = check_gate(scores=scores)
    message     = build_message(gate_result=gate_result)

    # Post to Slack (conn_id "slack_clinical" set in Airflow connections)
    SlackWebhookOperator(
        task_id="post_slack_report",
        slack_webhook_conn_id="slack_clinical",
        message=message,
    )


# clinical_eval_monitor()
