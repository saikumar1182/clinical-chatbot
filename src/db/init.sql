-- Enable pgvector extension
-- This is what makes PostgreSQL a vector database

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- For text search
CREATE EXTENSION IF NOT EXISTS pg_stat_statements; -- Query monitoring


-- Airflow needs its own database (separate from pharmachat)
CREATE DATABASE airflow;


-- Create schemas (medallion architecture)

CREATE SCHEMA IF NOT EXISTS bronze; -- Raw data from source
CREATE SCHEMA IF NOT EXISTS silver; -- Cleaned, standardized data
CREATE SCHEMA IF NOT EXISTS gold; -- Business-level, aggregated data
CREATE SCHEMA IF NOT EXISTS vectors; -- Vector embeddings for RAG
CREATE SCHEMA IF NOT EXISTS analytics; -- BI, reporting, dashboards

-- Raw Bronze table — stores JSON exactly as received

CREATE TABLE IF NOT EXISTS bronze.clinical_trials (
    id BIGSERIAL PRIMARY KEY,
    nct_id TEXT NOT NULL,
    raw_json JSONB NOT NULL,
    source_url TEXT,
    ingested_at TIMESTAMP DEFAULT NOW(),
    batch_id TEXT,      -- Which ingestion batch this record belongs to
    is_processed BOOLEAN DEFAULT FALSE
);

-- Index for incremental processing
CREATE INDEX IF NOT EXISTS idx_bronze_nct_id ON bronze.clinical_trials(nct_id);
CREATE INDEX IF NOT EXISTS idx_bronze_ingested_at ON bronze.clinical_trials(ingested_at);
CREATE INDEX IF NOT EXISTS idx_bronze_processed ON bronze.clinical_trials(is_processed);