"""
DAG 2: clinical_dbt
Schedule: None (triggered by clinical_ingestion DAG)
Purpose: Run dbt Bronze → Silver → Gold via Astronomer Cosmos

Replaces: subprocess.run(["dbt", "run"]) black box in run_ingestion.py
Key upgrade:
  - Each dbt model = one Airflow task (visible, retryable, with logs)
  - Task graph mirrors dbt ref() lineage automatically
  - dbt test failures set the task to FAILED → blocks DAG 3 (embeddings)
  - Click any model in the Airflow UI to see its SQL, execution time, logs
  - Retry a single failed model without re-running the whole pipeline
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

# ── Astronomer Cosmos imports ────────────────────────────────
from cosmos import DbtTaskGroup, ProjectConfig, ProfileConfig, ExecutionConfig
from cosmos.profiles import PostgresUserPasswordProfileMapping

# ── dbt project path inside the Airflow container ────────────
# Mounted via volumes: ./dbt_project:/opt/airflow/dbt_project
DBT_PROJECT_PATH = Path("/opt/airflow/dbt_project")
DBT_PROFILES_PATH = DBT_PROJECT_PATH   # profiles.yml lives alongside dbt_project.yml

# ── Cosmos profile: reads from Airflow Connection "clinical_postgres" ──
# Connection registered automatically in docker-compose airflow-init
profile_config = ProfileConfig(
    profile_name="clinical_chat",
    target_name="dev",
    profile_mapping=PostgresUserPasswordProfileMapping(
        conn_id="clinical_postgres",        # Created by airflow-init on startup
        profile_args={
            "schema": "silver",
            "dbname": os.getenv("POSTGRES_DB"),
        },
    ),
)

# ── Cosmos execution: dbt binary location in the Airflow container ────
execution_config = ExecutionConfig(
    dbt_executable_path="/opt/airflow/dbt_venv/bin/dbt",
)

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
    "email_on_failure": False,
    "email_on_retry": False,
}


@dag(
    dag_id="clinical_dbt",
    description=(
        "dbt Bronze→Silver→Gold via Astronomer Cosmos. "
        "Triggered by clinical_ingestion. Each dbt model = one Airflow task."
    ),
    schedule=None,                          # Triggered only — never self-schedules
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["clinical", "dbt", "cosmos", "transform"],
    doc_md="""
## clinical_dbt DAG (Astronomer Cosmos)

**What it does**: Runs dbt seed → bronze models → silver models → gold models
→ dbt tests. Each dbt model is a separate Airflow task.

**Triggered by**: `clinical_ingestion` DAG via TriggerDagRunOperator.

**Cosmos generates these tasks automatically from dbt_project/**:
```
seed.condition_categories
  └── raw.stg_raw_trials
        └── silver.int_trials_cleaned
              ├── silver.test.not_null_nct_id
              ├── silver.test.unique_nct_id
              ├── silver.test.accepted_values_status
              └── gold.trials_enriched
                    ├── gold.test.not_null_nct_id
                    └── gold.test.unique_nct_id
```

**Quality Gate**: If ANY dbt test fails, that task is marked FAILED.
The `trigger_embeddings_dag` task will NOT run — bad data never
reaches pgvector or the LLM context window.

**To retry a single model**: Click the failed task in the Airflow UI
→ "Clear" → it reruns only that model, not the whole pipeline.
    """,
)
def clinical_dbt():

    # ── Cosmos: auto-generates one Airflow task per dbt model + test ──
    # Dependencies are inferred from dbt ref() calls — no manual wiring needed
    # operator_args are passed to every generated DbtRunLocalOperator
    transform_group = DbtTaskGroup(
        group_id="dbt_pipeline",
        project_config=ProjectConfig(
            dbt_project_path=DBT_PROJECT_PATH,
            project_name="clinical_chat",
        ),
        profile_config=profile_config,
        execution_config=execution_config,
        operator_args={
            "install_deps": True,           # Run `dbt deps` before each model
            "full_refresh": False,          # Incremental by default
            "vars": {
                "execution_date": "{{ ds }}",   # Pass Airflow date to dbt
            },
            # dbt test failures fail the Airflow task (default is warn)
            "on_warning_callback": None,
        },
    )

    # ── Trigger embeddings DAG only if ALL dbt tasks succeed ──────
    # This is the quality gate: embeddings only update with clean Gold data
    trigger_embed = TriggerDagRunOperator(
        task_id="trigger_embeddings_dag",
        trigger_dag_id="clinical_embeddings",
        wait_for_completion=False,
        reset_dag_run=True,
        conf={"triggered_by": "clinical_dbt"},
    )

    transform_group >> trigger_embed


clinical_dbt()
