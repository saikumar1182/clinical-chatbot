"""
load_to_postgres.py — Bronze layer upsert.

Called by Airflow DAG 1 task function fetch_and_load().
Upserts raw trial JSON into raw.clinical_trials (Bronze).
ON CONFLICT resets is_processed=FALSE so dbt incremental picks it up.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text

from src.db.connection import engine

logger = logging.getLogger(__name__)


def load_trials_batch(
    trials: list[dict],
    batch_id: str,
    condition_tag: str = "",
) -> int:
    """
    Upsert a batch of raw trial dicts into raw.clinical_trials (Bronze).

    Strategy:
        INSERT ... ON CONFLICT (nct_id) DO UPDATE
        - New trial   → inserted fresh, is_processed=FALSE
        - Updated trial → JSON replaced, is_processed reset to FALSE
          so the dbt incremental model detects it and re-processes it

    Args:
        trials:        List of raw trial dicts from ClinicalTrials.gov API
        batch_id:      Airflow run_id fragment for lineage tracking
        condition_tag: Which condition search produced these trials

    Returns:
        Number of rows inserted or updated
    """
    if not trials:
        return 0

    rows = []
    for trial in trials:
        try:
            protocol = trial.get("protocolSection", {})
            nct_id = (
                protocol
                .get("identificationModule", {})
                .get("nctId", "")
            )
            if not nct_id:
                logger.warning(f"Skipping trial with no nctId: {str(trial)[:100]}")
                continue

            rows.append({
                "nct_id":        nct_id,
                "raw_json":      json.dumps(trial),
                "batch_id":      batch_id,
                "condition_tag": condition_tag,
                "source_url":    f"https://clinicaltrials.gov/study/{nct_id}",
            })
        except (KeyError, TypeError) as e:
            logger.warning(f"Malformed trial record, skipping: {e}")
            continue

    if not rows:
        logger.warning("No valid rows to insert after parsing")
        return 0

    UPSERT_SQL = """
        INSERT INTO raw.clinical_trials
            (nct_id, raw_json, batch_id, condition_tag, source_url)
        VALUES
            (:nct_id, CAST(:raw_json AS jsonb), :batch_id, :condition_tag, :source_url)
        ON CONFLICT (nct_id) DO UPDATE SET
            raw_json      = EXCLUDED.raw_json,
            batch_id      = EXCLUDED.batch_id,
            condition_tag = EXCLUDED.condition_tag,
            ingested_at   = NOW(),
            is_processed  = FALSE   -- Triggers dbt incremental re-processing
    """

    with engine.begin() as conn:
        result = conn.execute(text(UPSERT_SQL), rows)
        count = result.rowcount

    logger.info(f"Upserted {count}/{len(rows)} rows for batch '{batch_id}'")
    return count


def get_last_ingestion_time(condition: str | None = None) -> str | None:
    """
    Returns the ISO timestamp of the most recent ingestion.
    Used for logging/monitoring — Airflow's data_interval_start
    is the actual incremental cursor used in DAG 1.
    """
    from src.db.connection import execute_query

    if condition:
        rows = execute_query(
            "SELECT MAX(ingested_at) AS last_run FROM raw.clinical_trials WHERE condition_tag = :cond",
            {"cond": condition},
        )
    else:
        rows = execute_query(
            "SELECT MAX(ingested_at) AS last_run FROM raw.clinical_trials"
        )

    last_run = rows[0]["last_run"] if rows else None
    return last_run.isoformat() if last_run else None
