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
    "count", "list all", "show me all", "what are all", "how much", "how many", "average",
    "total", "sum", "min", "max", "distinct", "group by", "order by", "where", "having",
    "between", "in", "not in", "like", "not like", "is null", "is not null",
    "percentage", "rate", "ratio", "proportion", "distribution", "frequency",
    "median", "mode", "standard deviation", "variance", "correlation", "regression",
    "trend", "growth", "decline", "change", "difference", "comparison",
    "top", "bottom", "most", "least", "fewest", "greatest", "smallest",
    "by", "per", "among", "within", "across", "between", "amongst", "within", "across",
    "and", "or", "not", "if", "then", "when", "where", "while", "since", "until",
    "as", "at", "by", "for", "from", "in", "into", "like", "near", "of", "off",
    "on", "onto", "out", "over", "past", "through", "to", "toward", "under", "up",
    "with", "within", "without",
}

RAG_KEYWORDS = {
    "what is", "what does", "explain", "describe", "tell me about", "how does", "what are the results",
    "what happened", "why", "protocol", "eligibility", "what trial", "which trial", "summarise", "details of",
    "what is the status of", "what is the status of", "final results"
}

OOT_KEYWORDS = {
    "weather", "news today", "sports", "entertainment", "politics", "general knowledge",
    "recipe", "bitcoin", "stock market", "travel"
    
}

def route_query(query: str) -> QueryRoute:
    """Route the query to the appropriate handler."""
    query_lower = query.lower()

    # Check for OOT keywords
    if any(keyword in query_lower for keyword in OOT_KEYWORDS):
        return QueryRoute.OOT
    
    # Check for SQL keywords
    has_sql = any(keyword in query_lower for keyword in SQL_KEYWORDS)
    
    # Check for RAG keywords
    has_rag = any(keyword in query_lower for keyword in RAG_KEYWORDS)
    
    if has_sql and has_rag:
        return QueryRoute.HYBRID
    if has_sql:
        return QueryRoute.SQL
    return QueryRoute.RAG
        