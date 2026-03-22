import logging
from datetime import datetime, timedelta
from airflow.models import Variable
from airflow.decorators import dag, task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator


logger = logging.getLogger(__name__)

CONDITIONS = Variable.get(
    "pharmachat_conditions",
    default_var=["diabetes", "lung cancer", "alzheimer", "cardiovascular", "obesity"],
    deserialize_json=True,
)

default_args = {
    "owner": "data-team",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "email_on_failure": True,
    "email": ["maneeshsai1118@gmail.com"],
}

@dag(
    dag_id = "clinicalchat_ingestion",
    start_date = datetime(2026,3,23),
    schedule = "@daily",
    catchup = False,
    default_args = default_args,
    tags = ["clinicalchat", "ingestion", "bronze"],
    doc_md = """
    ### Clinical Chat Ingestion DAG
    This DAG ingests clinical trial data from the ClinicalTrials.gov API into the bronze layer.
    """
)

def clinicalchat_ingestion():
    @task(task_id="check_db_health")
    def check_db_health():
        from src.db.connection import execute_query
        result = execute_query(
            "SELECT COUNT(*) AS n FROM information_schema.schemata "
            "WHERE schema_name IN ('bronze','silver','gold','vectors')"
        )
        if result[0]["n"] < 4:
            raise ValueError("Schemas missing — run init.sql first")
        logger.info("DB health OK")
        return True
        
    @task(
        task_id="fetch_and_load_condition",
        pool="api_pool",               # Max 5 concurrent API calls
        retries=3,
        retry_delay=timedelta(minutes=5),
    )
    def fetch_and_load(condition: str, **context) -> dict:
        """
        Fetch one condition from ClinicalTrials.gov and upsert into Bronze.
        Uses Airflow's data_interval_start as the incremental cursor —
        no manual MAX(ingested_at) query needed (Airflow tracks this).
        """
        from src.ingestion.fetch_trials import fetch_trials_incremental
        from src.ingestion.load_to_postgres import load_trials_batch
        import uuid

        since_date = context["data_interval_start"] - timedelta(hours=1)
        batch_id = f"{context['run_id'][:8]}-{condition}"

        fetched, inserted = 0, 0
        for batch in fetch_trials_incremental(condition, since_date=since_date):
            fetched += len(batch)
            inserted += load_trials_batch(batch, batch_id=batch_id)

        logger.info(f"✓ {condition}: fetched={fetched}, inserted={inserted}")
        return {"condition": condition, "fetched": fetched, "inserted": inserted}

    @task(task_id="summarise_ingestion")
    def summarise(results: list[dict]) -> dict:
        total = {
            "total_fetched":  sum(r["fetched"]  for r in results),
            "total_inserted": sum(r["inserted"] for r in results),
        }
        logger.info(f"Ingestion complete: {total}")
        return total
    

    # trigger_dbt = TriggerDagRunOperator(
    #     task_id="trigger_dbt_dag",
    #     trigger_dag_id="pharmachat_dbt",
    #     wait_for_completion=False,
    #     reset_dag_run=True,
    # )

    health = check_db_health()
    results = fetch_and_load.expand(condition=CONDITIONS)
    summary = summarise(results)

    health >> results >> summary #>> trigger_dbt

clinicalchat_ingestion()