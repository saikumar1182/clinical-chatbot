"""
router.py — Routes user questions to RAG, SQL, Hybrid, or Out-of-Topic handler.
"""
from __future__ import annotations

from enum import Enum 

class QueryRoute(Enum):
    RAG = "rag"
    SQL = "sql"
    HYBRID = "hybrid"
    OOT = "out_of_topic"


SQL_KEYWORDS = {
    "count",
    "list all",
    "show me all",
    "how much",
    "how many",
    "average",
    "total",
    "sum",
    "min",
    "max",
    "distinct",
    "group by",
    "order by",
    "percentage",
    "rate",
    "ratio",
    "distribution",
    "frequency",
    "median",
    "mode",
    "standard deviation",
    "variance",
    "correlation",
    "regression",
    "trend",
    "growth",
    "decline",
    "difference",
    "comparison",
    "top",
    "bottom",
    "most",
    "least",
    "fewest",
    "greatest",
    "smallest",
}

RAG_KEYWORDS = {
    "what is",
    "what does",
    "explain",
    "describe",
    "tell me about",
    "how does",
    "what are the results",
    "what happened",
    "why",
    "protocol",
    "eligibility",
    "what trial",
    "which trial",
    "summarise",
    "details of",
    "what is the status of",
    "final results",
    "studying",
}

OOT_KEYWORDS = {
    "weather",
    "news today",
    "sports",
    "entertainment",
    "politics",
    "general knowledge",
    "recipe",
    "bitcoin",
    "stock market",
    "travel",
}


def route_query(query: str) -> QueryRoute:
    query_lower = query.lower().strip()

    if any(keyword in query_lower for keyword in OOT_KEYWORDS):
        return QueryRoute.OOT

    has_sql = any(keyword in query_lower for keyword in SQL_KEYWORDS)
    has_rag = any(keyword in query_lower for keyword in RAG_KEYWORDS)

    if has_sql and has_rag:
        return QueryRoute.HYBRID
    if has_sql:
        return QueryRoute.SQL
    if has_rag:
        return QueryRoute.RAG
    return QueryRoute.RAG