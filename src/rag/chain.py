"""
chain.py — Full LangChain RAG + SQL pipeline.
Entry point for all Streamlit chat queries.
"""
from __future__ import annotations

import os
import logging
import time
import uuid
from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_aws import ChatBedrock

from src.llm.router import route_query, QueryRoute
from src.prompts.prompts_registry import get_prompt
from src.rag.retriever import retrieve_relevant_chunks


logger = logging.getLogger(__name__)

@dataclass
class ChatResponse:
    answer: str
    sources: list[dict]
    query_type: str
    prompt_version: str
    sql_query: str | None
    trace_id: str
    latency_ms: int

_llm: ChatBedrock | None = None

# Lazy load LLM
# Temperature: Controls randomness. 0.1 = deterministic, 0.7 = creative
# Max Tokens: Maximum number of tokens to generate. 512 = ~384 words
# top_p: Nucleus sampling. 0.1 = very conservative, 0.9 = very creative
# top_k: Sample the top k most likely tokens in each step

def _get_llm() -> ChatBedrock:
    global _llm
    if _llm is None:
        _llm = ChatBedrock(
            provider="anthropic",
            model_id=os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"),
            model_kwargs={"temperature": 0.1, "max_tokens": 1024, "top_k": 30},
            region_name=os.getenv("AWS_REGION"),
        )
    return _llm


# Format the context as a list of NCT IDs and similarity scores
# This will help the LLM to identify the relevant information
def _format_context(docs: list) -> str:
    if not docs:
        return "No relevant trials found in the database."
    
    parts = []
    for doc in docs:
        nct = doc.metadata.get("nct_id", "UNKNOWN")
        sim = doc.metadata.get("similarity", 0.0)
        parts.append(f"""[NCT ID: {nct}] [Similarity: {sim:.2f}]\n{doc.page_content}\n""")
    return "\n\n---\n\n".join(parts)


def _format_sql_result(result) -> str:
    """Format SQL results safely for prompt context."""
    if result is None:
        return "No rows returned."

    if isinstance(result, str):
        return result.strip() or "No rows returned."

    if isinstance(result, (int, float, bool)):
        return str(result)

    if isinstance(result, dict):
        return "\n".join(f"{k}: {v}" for k, v in result.items())

    if isinstance(result, (list, tuple)):
        if not result:
            return "No rows returned."

        lines = []
        for i, row in enumerate(result[:50], start=1):
            if isinstance(row, dict):
                line = ", ".join(f"{k}={v}" for k, v in row.items())
            elif isinstance(row, (list, tuple)):
                line = ", ".join(str(x) for x in row)
            else:
                line = str(row)
            lines.append(f"{i}. {line}")

        if len(result) > 50:
            lines.append(f"... and {len(result) - 50} more rows")

        return "\n".join(lines)

    return str(result)


def ask(
    question: str,
    prompt_version: str = "v4",
    filters: dict | None = None,
    
) -> ChatResponse:
    start_time = time.time()
    trace_id = str(uuid.uuid4())
    query_type = route_query(question)
    
    if query_type == QueryRoute.OOT:
        return ChatResponse(
            answer="""I am specialised in clinical trial data only.
            I can only answer questions about clinical trials. Please ask a question about clinical trials.""",
            sources=[],
            query_type=query_type.value,
            sql_query=None,
            prompt_version=prompt_version,
            trace_id=trace_id,
            latency_ms=0,
        )
    sources: list[dict] = []
    sql_query: str | None = None
    
    if query_type == QueryRoute.SQL:
        from src.llm.text_to_sql import execute_text_to_sql
        result, sql_query = execute_text_to_sql(question)
        context_text = (
            f"SQL Query:\n{sql_query}\n\n"
            f"SQL Result:\n{_format_sql_result(result)}"
        )

        logger.info("SQL Query executed: %s", sql_query)
        logger.info("SQL Result: %s", result)
    else:
        docs = retrieve_relevant_chunks(
            query=question,
            top_k=5,
            filter_by=filters,
            similarity_threshold=0.3
        )
        logger.info(f"Retrieved {len(docs)} documents")
        logger.info(f"Documents: {docs}")

        context_text = _format_context(docs)
        sources = [
            {
                "nct_id": doc.metadata.get("nct_id"), 
                "similarity": doc.metadata.get("similarity"),
                "status": doc.metadata.get("status"),
                "therapeutic_area": doc.metadata.get("therapeutic_area"),
            }
            for doc in docs
        ]
        if not docs:
            latency_ms = int((time.time() - start_time) * 1000)
            answer = "I cannot find this in the available trial data."

            try:
                from src.evaluation.weave_tracer import log_llm_traces
                log_llm_traces(
                    trace_id=trace_id,
                    question=question,
                    answer=answer,
                    sources=sources,
                    prompt_version=prompt_version,
                    latency_ms=latency_ms,
                    context="No relevant trials found in the database.",
                    query_type=query_type.value,
                )
            except Exception as e:
                logger.error(f"Failed to log LLM traces: {e}")

            return ChatResponse(
                answer=answer,
                sources=[],
                query_type=query_type.value,
                prompt_version=prompt_version,
                sql_query=None,
                trace_id=trace_id,
                latency_ms=latency_ms,
            )
    
    sys_prompt, human_text = get_prompt(prompt_version)

    chain = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(sys_prompt),
        HumanMessagePromptTemplate.from_template(human_text),
    ]) | _get_llm() | StrOutputParser()
    
    answer = chain.invoke({
        "context": context_text,
        "question": question,
    })
    
    latency_ms = int((time.time() - start_time) * 1000)

    logger.info(f"Answer: {answer}")
    logger.info(f"Sources: {sources}")
    logger.info(f"Query Type: {query_type}")
    logger.info(f"Prompt Version: {prompt_version}")
    logger.info(f"Trace ID: {trace_id}")
    logger.info(f"Latency: {latency_ms}")
    logger.info(f"Context: {context_text}")
    
    try:
        from src.evaluation.weave_tracer import log_llm_traces
        log_llm_traces(
            trace_id=trace_id,
            question=question,
            answer=answer,
            sources=sources,
            prompt_version=prompt_version,
            latency_ms=latency_ms,
            context=context_text,
            query_type=query_type.value,
        )
    except Exception as e:
        logger.error(f"Failed to log LLM traces: {e}")
    
    return ChatResponse(
        answer=answer,
        sources=sources,
        query_type=query_type.value,
        prompt_version=prompt_version,
        sql_query=sql_query,
        trace_id=trace_id,
        latency_ms=latency_ms,
    )