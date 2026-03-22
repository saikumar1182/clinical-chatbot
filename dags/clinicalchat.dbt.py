from datetime import datetime, timedelta
from pathlib import Path
import os

from airflow.decorators import dag
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

# Astronomer Cosmos imports
from cosmos import DbtTaskGroup, ProjectConfig, ProfileConfig, ExecutionConfig
from cosmos.profiles import PostgresUserPasswordProfileMapping

DBT_PROJECT_PATH = Path("/opt/airflow/dbt")

# Cosmos reads Airflow Connection "clinicalchat_postgres" set in init
profile_config = ProfileConfig(
    profile_name="clinicalchat",
    target_name="dev",
    profile_mapping=PostgresUserPasswordProfileMapping(
        conn_id="clinicalchat_postgres",
        profile_args={
            "schema": "silver",
            "dbname": os.getenv("POSTGRES_DB", "clinicaldb"),
        },
    ),
)

execution_config = ExecutionConfig(dbt_executable_path="/usr/local/bin/dbt")

@dag(
    dag_id="clinicalchat_dbt",
    description="dbt Bronze→Silver→Gold via Astronomer Cosmos. Triggered by ingestion DAG.",
    schedule=None,                    # Triggered only — never self-schedules
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        "owner": "data-team",
        "retries": 2,
        "retry_delay": timedelta(minutes=3),
        "email_on_failure": True,
        "email": ["maneeshsai1118@gmail.com"],
    },
    tags=["clinicalchat", "dbt", "cosmos"],
)
def clinicalchat_dbt():

    # Cosmos auto-generates tasks for every dbt model + test in dbt_project/
    # Task graph mirrors dbt ref() lineage: bronze → silver → gold → tests
    # If ANY dbt test fails, that task is FAILED → embeddings DAG not triggered
    transform_group = DbtTaskGroup(
        group_id="dbt_pipeline",
        project_config=ProjectConfig(
            dbt_project_path=DBT_PROJECT_PATH,
            project_name="pharmachat",
        ),
        profile_config=profile_config,
        execution_config=execution_config,
        operator_args={
            "install_deps": True,
            "full_refresh": False,   # Incremental by default
            "vars": {"execution_date": "{{ ds }}"},
        },
    )

    # trigger_embed = TriggerDagRunOperator(
    #     task_id="trigger_embeddings_dag",
    #     trigger_dag_id="pharmachat_embeddings",
    #     wait_for_completion=False,
    # )

    transform_group #>> trigger_embed

clinicalchat_dbt()