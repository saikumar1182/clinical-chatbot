from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import get_current_context

logger = logging.getLogger(__name__)

default_args = {
    "owner": "data-engineering",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "email_on_failure": False,
    "email_on_retry": False,
}


@dag(
    dag_id="clinical_ingestion",
    description="Fetch ClinicalTrials.gov data → PostgreSQL Bronze",
    schedule="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["clinical", "ingestion", "bronze"],
)
def clinical_ingestion():
    conditions = Variable.get(
        "clinical_conditions",
        default_var=[
            "lung cancer",
            "diabetes",
        ],
        deserialize_json=True,
    )

    @task(task_id="check_db_health")
    def check_db_health() -> bool:
        hook = PostgresHook(postgres_conn_id="clinical_postgres")

        ok = hook.get_first("SELECT 1")
        if not ok:
            raise ConnectionError("PostgreSQL is not reachable via Airflow connection 'clinical_postgres'.")

        found = hook.get_first(
            """
            SELECT COUNT(*)
            FROM information_schema.schemata
            WHERE schema_name IN ('raw', 'silver', 'gold', 'vectors', 'eval')
            """
        )[0]

        if found < 5:
            raise ValueError(
                f"Only {found}/5 required schemas exist. "
                "Did src/db/init.sql run on first Postgres start?"
            )

        logger.info("DB health check passed — all schemas present")
        return True

    @task(
        task_id="fetch_and_load_condition",
        pool="api_pool",
        retries=3,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
    )
    def fetch_and_load(condition: str) -> dict[str, Any]:
        from src.ingestion.fetch_trials import fetch_trials_incremental
        from src.ingestion.load_to_postgres import load_trials_batch

        context = get_current_context()
        data_interval_start = context["data_interval_start"]
        run_id = context["run_id"]

        since_date = data_interval_start - timedelta(days=60)
        batch_id = f"{run_id[:12]}-{condition}"

        logger.info(
            "Fetching %s | since=%s | batch=%s",
            condition,
            since_date.isoformat(),
            batch_id,
        )

        fetched_total = 0
        inserted_total = 0

        for batch in fetch_trials_incremental(
            condition=condition,
            since_date=since_date,
        ):
            fetched_total += len(batch)
            inserted = load_trials_batch(
                trials=batch,
                batch_id=batch_id,
                condition_tag=condition,
            )
            inserted_total += inserted

        summary = {
            "condition": condition,
            "fetched": fetched_total,
            "inserted": inserted_total,
            "batch_id": batch_id,
        }
        logger.info("Done %s: fetched=%s upserted=%s", condition, fetched_total, inserted_total)
        return summary

    @task(task_id="summarise_ingestion")
    def summarise(results: list[dict[str, Any]]) -> dict[str, int]:
        total_fetched = sum(r.get("fetched", 0) for r in results)
        total_inserted = sum(r.get("inserted", 0) for r in results)

        logger.info("INGESTION SUMMARY")
        logger.info("Conditions: %s", len(results))
        logger.info("Fetched: %s", total_fetched)
        logger.info("Upserted: %s", total_inserted)

        return {
            "total_fetched": total_fetched,
            "total_inserted": total_inserted,
            "conditions": len(results),
        }

    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt_dag",
        trigger_dag_id="clinical_dbt",
        wait_for_completion=False,
        reset_dag_run=True,
        conf={"triggered_by": "clinical_ingestion"},
    )

    health = check_db_health()
    condition_results = fetch_and_load.expand(condition=conditions)
    summary = summarise(results=condition_results)

    health >> condition_results >> summary >> trigger_dbt


clinical_ingestion()