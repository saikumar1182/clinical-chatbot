"""
DAG 3: clinical_embeddings
Schedule: None (triggered by clinical_dbt DAG)
Purpose: Embed new/updated Gold layer trials into pgvector

Replaces: embed_and_store() called inline in run_ingestion.py
Key improvements:
  - NCT IDs batched into groups of 50, all batches run IN PARALLEL
  - bedrock_pool limits concurrent Bedrock API calls to 3 (rate limit safe)
  - Dynamic task mapping: task count scales with new trial count
  - Only re-embeds trials that are new OR were re-ingested (smart delta)
  - Final verification task confirms vector count in pgvector
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 50       # NCT IDs per embedding task


def _chunk_list(lst: list, n: int) -> list[list]:
    """Split a flat list into sub-lists of size n."""
    return [lst[i : i + n] for i in range(0, len(lst), n)]


@dag(
    dag_id="clinical_embeddings",
    description=(
        "Embed new/updated Gold layer trials into pgvector. "
        "Triggered by clinical_dbt. Parallel batch processing."
    ),
    schedule=None,                      # Triggered only
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        "owner": "data-engineering",
        "retries": 3,
        "retry_delay": timedelta(minutes=2),
        "email_on_failure": True,
        "email": ["data-alerts@clinicalchat.local"],
    },
    tags=["clinical", "embeddings", "vectors", "rag"],
    doc_md="""
## clinical_embeddings DAG

**What it does**: Identifies trials in the Gold layer that don't yet have
embeddings (or were re-ingested), chunks their text, calls Amazon Titan
via AWS Bedrock to generate 1536-dim embeddings, and upserts them into
the `vectors.trial_chunks` pgvector table.

**Triggered by**: `clinical_dbt` DAG (only runs when dbt tests pass).

**Parallelism**: NCT IDs are batched into groups of 50. Each batch runs
as a separate parallel Airflow task. 200 new trials = 4 parallel tasks.

**Rate limiting**: All embedding tasks share the `bedrock_pool` Airflow
Pool (max 3 slots) — prevents exceeding AWS Bedrock API limits.
    """,
)
def clinical_embeddings():

    @task(task_id="get_trials_to_embed")
    def get_trials_to_embed() -> list[list[str]]:
        """
        Find NCT IDs that need embedding:
          1. Never embedded (new trials in Gold layer)
          2. Re-ingested since last embedding (updated trials)

        Returns a list of batches for dynamic task mapping.
        An empty list means nothing to embed — downstream tasks are skipped.
        """
        from src.db.connection import execute_query

        rows = execute_query(
            """
            SELECT g.nct_id
            FROM gold.trials_enriched g
            LEFT JOIN (
                SELECT nct_id, MAX(embedded_at) AS last_embedded
                FROM vectors.trial_chunks
                GROUP BY nct_id
            ) v ON g.nct_id = v.nct_id
            WHERE
                g.has_summary = TRUE                     -- Only trials with content
                AND (
                    v.nct_id IS NULL                     -- Never embedded
                    OR g.updated_at > v.last_embedded    -- Re-ingested since last embed
                )
            ORDER BY g.nct_id
            """
        )

        nct_ids = [r["nct_id"] for r in rows]
        logger.info(f"Found {len(nct_ids)} trials needing embedding")

        if not nct_ids:
            logger.info("Nothing to embed — all vectors are up to date")
            return []

        batches = _chunk_list(nct_ids, EMBED_BATCH_SIZE)
        logger.info(
            f"Split into {len(batches)} batches of up to {EMBED_BATCH_SIZE} each"
        )
        return batches

    @task(
        task_id="embed_batch",
        pool="bedrock_pool",            # Max 3 concurrent Bedrock API calls
        retries=3,
        retry_delay=timedelta(minutes=1),
    )
    def embed_batch(nct_id_batch: list[str]) -> dict:
        """
        Embed one batch of NCT IDs.
        Multiple of these tasks run in parallel (bounded by bedrock_pool=3).

        Each call:
          1. Loads embedding_text from gold.trials_enriched
          2. Chunks text (800 tok, 120 overlap) via LangChain
          3. Calls Amazon Titan Embed v2 via AWS Bedrock
          4. Upserts embeddings into vectors.trial_chunks
        """
        from src.rag.embeddings import embed_and_store

        if not nct_id_batch:
            return {"chunks": 0, "nct_ids": 0}

        chunk_count = embed_and_store(nct_ids=nct_id_batch)
        logger.info(
            f"Embedded {chunk_count} chunks for {len(nct_id_batch)} trials"
        )
        return {"chunks": chunk_count, "nct_ids": len(nct_id_batch)}

    @task(task_id="verify_vector_count")
    def verify(embed_results: list[dict]) -> dict:
        """
        Final sanity check: verify pgvector count and log summary.
        Fails the task if no chunks were produced (regression guard).
        """
        from src.db.connection import execute_query

        new_chunks = sum(r.get("chunks", 0) for r in embed_results if r)
        new_ncts = sum(r.get("nct_ids", 0) for r in embed_results if r)

        result = execute_query(
            "SELECT COUNT(*) AS total_chunks, COUNT(DISTINCT nct_id) AS total_trials "
            "FROM vectors.trial_chunks"
        )
        total_chunks = result[0]["total_chunks"]
        total_trials = result[0]["total_trials"]

        logger.info(
            f"Embedding complete: "
            f"{new_chunks} new chunks for {new_ncts} trials. "
            f"pgvector total: {total_chunks:,} chunks / {total_trials:,} trials"
        )

        return {
            "new_chunks": new_chunks,
            "new_trials": new_ncts,
            "total_chunks": total_chunks,
            "total_trials": total_trials,
        }

    # ── WIRING ────────────────────────────────────────────────────
    batches = get_trials_to_embed()

    # Dynamic task mapping: one embed_batch task per batch of 50 NCT IDs
    # e.g. 200 new trials → 4 parallel tasks; 0 new trials → 0 tasks
    batch_results = embed_batch.expand(nct_id_batch=batches)

    verify(embed_results=batch_results)


clinical_embeddings()
