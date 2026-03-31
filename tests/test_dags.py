"""DAG unit tests — runs in CI to catch broken DAGs before merge."""
import os
import pytest

os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "false")
os.environ.setdefault("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "sqlite:////tmp/test_airflow.db")
os.environ.setdefault("AIRFLOW__CORE__FERNET_KEY", "81HqDtbqAywKSOumSha3BhWNOdQ26slT6K0YaZeZyPs=")


@pytest.fixture(scope="module")
def dag_bag():
    from airflow.models import DagBag
    return DagBag(dag_folder="dags/", include_examples=False)


class TestDagRegistration:
    def test_no_import_errors(self, dag_bag):
        assert not dag_bag.import_errors, f"DAG import errors: {dag_bag.import_errors}"

    def test_all_four_dags_registered(self, dag_bag):
        expected = {
            "clinical_ingestion",
            "clinical_dbt",
            "clinical_embeddings",
            "clinical_eval_monitor",
        }
        assert expected.issubset(set(dag_bag.dags.keys())), (
            f"Missing DAGs: {expected - set(dag_bag.dags.keys())}"
        )


class TestDagSchedules:
    def test_ingestion_schedule(self, dag_bag):
        dag = dag_bag.get_dag("clinical_ingestion")
        assert dag.schedule == "0 2 * * *"

    def test_dbt_no_self_schedule(self, dag_bag):
        dag = dag_bag.get_dag("clinical_dbt")
        assert dag.schedule is None, (
            "dbt DAG should only be triggered, not scheduled"
        )

    def test_embeddings_no_self_schedule(self, dag_bag):
        dag = dag_bag.get_dag("clinical_embeddings")
        assert dag.schedule is None

    def test_eval_schedule(self, dag_bag):
        dag = dag_bag.get_dag("clinical_eval_monitor")
        assert dag.schedule == "0 6 * * 0"


class TestIngestionDagMetadata:
    def test_ingestion_retries(self, dag_bag):
        dag = dag_bag.get_dag("clinical_ingestion")
        assert dag.default_args["retries"] >= 3

    def test_ingestion_owner(self, dag_bag):
        dag = dag_bag.get_dag("clinical_ingestion")
        assert dag.default_args["owner"] == "data-engineering"

    def test_ingestion_tags(self, dag_bag):
        dag = dag_bag.get_dag("clinical_ingestion")
        assert "bronze" in dag.tags
        assert "clinical" in dag.tags