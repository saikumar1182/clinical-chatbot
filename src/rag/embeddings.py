from __future__ import annotations

import os
import json
import logging

import boto3 # AWS SDK for Bedrock
from langchain_core.documents import Document # Stores a piece of text + metadata
from langchain_text_splitters import RecursiveCharacterTextSplitter # Splits text into chunks

from sqlalchemy import text
from src.db.connection import engine, execute_query # Database connection


logger = logging.getLogger(__name__)


SPLITTER = RecursiveCharacterTextSplitter(
    separators=["\n\n", "\n", ".", " "],
    chunk_size=800,
    chunk_overlap=120,
    length_function=len,
)

client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION"))

def embed_text(text: str) -> list[float]:
    response = client.invoke_model(
        modelId = "amazon.titan-embed-text-v2:0",
        body = json.dumps({
            "inputText": text,
            "normalize": True
        }),
        contentType = "application/json"
    )
    response_body = json.loads(response["body"].read())
    return response_body["embedding"]


def embed_store(nct_ids: list[str]| None = None) -> int:
    """Embed and store trial text in the database."""
    
    params = {}
    filter_clause = ""
    if nct_ids:
        filter_clause = "AND nct_id = ANY(:nct_ids)"
        params["nct_ids"] = nct_ids
    
    trials = execute_query(
        f"""
            SELECT nct_id, embedding_text, status, phase_num, therapeutic_area, condition_tag, sponsor, updated_at
            FROM gold.trials_enriched
            WHERE has_summary = TRUE {filter_clause}
            ORDER BY nct_id
        """,
        params,
    )

    if not trials:
        logger.info("No trials found to embed.")
        return 0

    total_chunks = 0
    with engine.begin() as conn:
        for trial in trials:
            nct_id = trial["nct_id"]
            
            conn.execute(
                text("DELETE FROM vectors.trial_chunks WHERE nct_id = :nct_id"),
                {"nct_id": nct_id},
            )

        docs = Document(
            page_content = trial["embedding_text"],
            metadata = {
                "nct_id": nct_id,
                "status": trial["status"],
                "phase": trial["phase_num"],
                "therapeutic_area": trial["therapeutic_area"],
                "condition": trial["condition_tag"],
                "sponsor": trial["sponsor"]
            },
        )
        
        chunks = SPLITTER.split_documents([docs])
        for i, chunk in enumerate(chunks):
            embedding = embed_text(chunk.page_content)
            conn.execute(
                text("""
                    INSERT INTO vectors.trial_chunks (
                        nct_id,
                        chunk_index,
                        chunk_text,
                        embedding,
                        metadata)
                    VALUES (:nct_id, :idx, :txt, CAST(:emb AS vector), CAST(:meta AS jsonb))
                    ON CONFLICT (nct_id, chunk_index) DO UPDATE SET
                        chunk_text = EXCLUDED.chunk_text,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                """),
                {
                    "nct_id": nct_id,
                    "idx": i,
                    "txt": chunk.page_content,
                    "emb": str(embedding),
                    "meta": json.dumps(chunk.metadata),
                },
            )
            total_chunks += 1

    logger.info(f"Embedded {total_chunks} chunks from {len(trials)} trials.")
    return total_chunks
                
                    
                    
    
    