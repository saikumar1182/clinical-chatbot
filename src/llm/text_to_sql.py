"""
text_to_sql.py — Convert natural language to PostgreSQL SQL and execute it.
"""
from __future__ import annotations

import os
import logging
import boto3

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_aws import ChatBedrock

logger = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "eu-west-3")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0")

bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

TEXT_TO_SQL_PROMPT = PromptTemplate(
    input_variables=["question"],
    template="""
    You are a PostgreSQL expert.
    Convert the user's question into a PostgreSQL query that can be executed against the database.

    DATABASE SCHEMA: gold.trials_enriched
    Columns: nct_id TEXT, title TEXT, status TEXT, phase_num INTEGER,
         brief_summary TEXT, conditions JSONB, sponsor TEXT,
         enrollment_count INTEGER, submit_date DATE, completion_date DATE,
         therapeutic_area TEXT, is_active BOOLEAN, is_completed BOOLEAN,
         submit_year INTEGER, duration_months INTEGER

    STATUS values: COMPLETED, RECRUITING, ACTIVE_NOT_RECRUITING,
               NOT_YET_RECRUITING, TERMINATED, WITHDRAWN
    RULES:
    - PostgreSQL syntax only. Use ILIKE for case-insensitive text.
    - Always add LIMIT 1000 unless aggregating.
    - NEVER write DELETE, UPDATE, DROP, TRUNCATE, INSERT, ALTER.
    - Output ONLY the SQL query, nothing else.

    Question: {question}

    SQL Query:
""")

def execute_text_to_sql(question: str) -> tuple[str, str]:
    """
    Execute the text-to-sql chain.

    Args:
        question: The question to convert to SQL.

    Returns:
        A tuple containing the SQL query and the result of the query.
    """
    
    llm = ChatBedrock(
        provider="anthropic",
        model=BEDROCK_MODEL_ID,
        region_name=AWS_REGION,
        model_kwargs={"temperature": 0.0, "max_tokens": 1024},
        
    )

    chain = TEXT_TO_SQL_PROMPT | llm | StrOutputParser()
    sql_query = chain.invoke({"question": question}).strip()
    sql = sql_query.replace("```sql", "").replace("```", "").strip()
    
    try:
        from src.db.connection import execute_query
        rows = execute_query(sql)
        result = str(rows[:50]) if rows else "No results found."
        logger.info(f"SQL query executed successfully: {sql}")
        
    except Exception as e:
        logger.error(f"Error executing SQL query: {e}")
        return sql, f"Error: {str(e)}"
    
    return result, sql
    
    
    
        

