-- ═══════════════════════════════════════════════════════════════════
-- ClinicalChat QA — PostgreSQL Initialisation Script
-- Auto-runs when the pgvector container starts for the first time
-- ═══════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;          -- Vector similarity search
CREATE EXTENSION IF NOT EXISTS pg_trgm;         -- Fuzzy text search
CREATE EXTENSION IF NOT EXISTS pg_stat_statements; -- Query performance monitoring
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- UUID generation

-- ── Airflow needs its own database ────────────────────────────
-- Airflow metadata (DAG runs, task instances, XComs, connections)
CREATE DATABASE airflow;

-- ── Medallion Architecture Schemas ────────────────────────────
CREATE SCHEMA IF NOT EXISTS raw;      -- Bronze: raw API data as-received
CREATE SCHEMA IF NOT EXISTS silver;   -- Silver: cleaned, tested, typed
CREATE SCHEMA IF NOT EXISTS gold;     -- Gold:   analytics-ready, enriched
CREATE SCHEMA IF NOT EXISTS vectors;  -- Vector: pgvector embeddings
CREATE SCHEMA IF NOT EXISTS eval;     -- Eval:   LLM traces, user ratings

-- ═══════════════════════════════════════════════════════════════════
-- BRONZE LAYER — raw.clinical_trials
-- Stores exactly what the ClinicalTrials.gov API returns (JSONB)
-- Append-only with upsert on nct_id
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS raw.clinical_trials (
    id              BIGSERIAL PRIMARY KEY,
    nct_id          TEXT NOT NULL,
    raw_json        JSONB NOT NULL,
    source_url      TEXT,
    condition_tag   TEXT,                   -- Which condition was fetched (diabetes, cancer...)
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    batch_id        TEXT,                   -- Groups all rows from one Airflow run
    is_processed    BOOLEAN DEFAULT FALSE,  -- Set FALSE on re-ingest → triggers dbt incremental
    CONSTRAINT raw_clinical_trials_nct_id_unique UNIQUE (nct_id)
);

-- Indexes for incremental processing
CREATE INDEX IF NOT EXISTS idx_raw_nct_id ON raw.clinical_trials(nct_id);
CREATE INDEX IF NOT EXISTS idx_raw_processed ON raw.clinical_trials(is_processed, ingested_at);
CREATE INDEX IF NOT EXISTS idx_raw_condition ON raw.clinical_trials(condition_tag);
CREATE INDEX IF NOT EXISTS idx_raw_batch ON raw.clinical_trials(batch_id);

-- ═══════════════════════════════════════════════════════════════════
-- VECTOR STORE — vectors.trial_chunks
-- pgvector table: stores text chunks + 1536-dim Titan embeddings
-- HNSW index for fast approximate nearest neighbour search
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS vectors.trial_chunks (
    id              BIGSERIAL PRIMARY KEY,
    nct_id          TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(1536),           -- Amazon Titan Embed v2 dimensions
    metadata        JSONB,                  -- status, phase, condition, sponsor, therapeutic_area
    embedded_at     TIMESTAMPTZ DEFAULT NOW(),
    chunk_strategy  TEXT DEFAULT 'recursive_800_120', -- Track chunking config version
    CONSTRAINT vectors_trial_chunks_unique UNIQUE (nct_id, chunk_index)
);

-- HNSW index — O(log n) approximate nearest neighbour
-- m=16: number of connections per node (memory vs recall)
-- ef_construction=64: search width during index build
CREATE INDEX IF NOT EXISTS idx_chunks_hnsw_embedding
    ON vectors.trial_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index on metadata for filtered vector search
CREATE INDEX IF NOT EXISTS idx_chunks_metadata
    ON vectors.trial_chunks USING gin(metadata);

CREATE INDEX IF NOT EXISTS idx_chunks_nct_id ON vectors.trial_chunks(nct_id);

-- ═══════════════════════════════════════════════════════════════════
-- EVALUATION LAYER — eval.traces
-- Every LLM call is logged here (from weave_tracer.py)
-- Used by Streamlit page 4 and DAG 4 (eval monitor)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS eval.traces (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL UNIQUE,
    question        TEXT NOT NULL,
    answer          TEXT,
    query_type      TEXT,                   -- rag / sql / hybrid / oot
    retrieved_ncts  TEXT[],                 -- NCT IDs cited in answer
    prompt_version  TEXT,
    faithfulness    FLOAT,                  -- 0.0–1.0 (LLM-as-judge score)
    relevance       FLOAT,
    latency_ms      INTEGER,
    token_count     INTEGER,
    user_rating     SMALLINT,               -- 1=thumbs up, -1=thumbs down, NULL=unrated
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traces_created ON eval.traces(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traces_prompt ON eval.traces(prompt_version);
CREATE INDEX IF NOT EXISTS idx_traces_rating ON eval.traces(user_rating) WHERE user_rating IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════════
-- INGESTION AUDIT — eval.ingestion_runs
-- Tracks every Airflow ingestion run for monitoring
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS eval.ingestion_runs (
    id              BIGSERIAL PRIMARY KEY,
    batch_id        TEXT NOT NULL UNIQUE,
    airflow_run_id  TEXT,
    conditions      TEXT[],
    total_fetched   INTEGER DEFAULT 0,
    total_inserted  INTEGER DEFAULT 0,
    dbt_passed      BOOLEAN,
    chunks_embedded INTEGER DEFAULT 0,
    duration_secs   FLOAT,
    status          TEXT DEFAULT 'running',  -- running / success / failed
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);

-- Grant access to application user
DO $$
BEGIN
    -- Grant schema usage
    EXECUTE format('GRANT USAGE ON SCHEMA raw, silver, gold, vectors, eval TO %I',
                   current_user);
    -- Grant table permissions
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw TO %I',
                   current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA vectors TO %I',
                   current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA eval TO %I',
                   current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA raw TO %I',
                   current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA vectors TO %I',
                   current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA eval TO %I',
                   current_user);
END $$;
