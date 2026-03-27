from __future__ import annotations

import json
import logging

from langchain_core.documents import Document 

from src.db.connection import execute_query
from src.rag.embeddings import embed_text


logger = logging.getLogger(__name__)

def retrieve_relevent_chunks(
    query: str,
    top_k: int = 5,
    filter_by: dict | None = None,
    similarity_threshold: float = 0.7,
) -> list[Document]:
    """
    Retrieve relevant chunks from the database based on query similarity.

    Args:
        query: The query to embed and compare against the database.
        top_k: The number of chunks to retrieve.
        filter_by: Optional dictionary of filters to apply to the query.
        similarity_threshold: The minimum similarity score to consider a chunk relevant.

    Returns:
        List of relevant Document objects.
    """
    
    query_embedding = embed_text(query)
    params: dict = {
        "query_embedding": str(query_embedding),
        "top_k": top_k,
        "similarity_threshold": 1 - similarity_threshold, # Convert similarity to distance for pgvector
    }

    filter_clauses = []
    if filter_by:
        for key, value in filter_by.items():
            filter_clauses.append(
                f"metadata @> '{{ \"{key}\": {json.dumps(value)} }}'::jsonb" # JSONB containment operator
            )
    
    where_extra = (" AND " + " AND ".join(filter_clauses)) if filter_clauses else ""

    data_rows = execute_query(
        f"""
        SELECT 
            chunk_text,
            metadata,
            nct_id,
            1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
        FROM vectors.trial_chunks
        WHERE
            (embedding <=> CAST(:query_embedding AS vector)) < :similarity_threshold
            {where_extra}
        ORDER BY embedding <=> CAST(:query_embedding AS vector)
        LIMIT :top_k
        """,
        params,
    )

    logger.info(f"Retrieved {len(data_rows)} chunks for query: {query}")
    
    return [
        Document(
            page_content=row["chunk_text"],
            metadata={
                **row["metadata"],
                "nct_id": row["nct_id"],
                "similarity": round(row["similarity"], 4),
            },
        )
        for row in data_rows
    ]