"""
Database connection module.
Provides a singleton SQLAlchemy engine and helper functions.
Used by both the Streamlit app and Airflow DAG task functions.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# DATABASE URL — resolves from env with sensible local default
# ─────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL",f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@localhost:5432/{os.getenv('POSTGRES_DB')}")

# ─────────────────────────────────────────────────────────────
# ENGINE — connection pool shared across the process
# ─────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,           # Permanent connections kept open
    max_overflow=20,        # Extra connections under load
    pool_timeout=30,        # Seconds to wait for a connection
    pool_recycle=1800,      # Recycle connections every 30 min
    pool_pre_ping=True,     # Validate connection before use
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_db_session():
    """Context manager that yields a SQLAlchemy session and handles cleanup."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def execute_query(sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    """
    Execute a raw SQL query and return results as a list of dicts.

    Args:
        sql: SQL string, may contain :param_name placeholders
        params: Dict of parameter values

    Returns:
        List of row dicts
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result]


def execute_write(sql: str, params: dict[str, Any] | None = None) -> int:
    """
    Execute a write query (INSERT/UPDATE/DELETE) inside a transaction.

    Returns:
        Row count affected
    """
    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        return result.rowcount


def execute_write_many(sql: str, rows: list[dict]) -> int:
    """
    Execute a write query for multiple rows (batch upsert).

    Returns:
        Row count affected
    """
    if not rows:
        return 0
    with engine.begin() as conn:
        result = conn.execute(text(sql), rows)
        return result.rowcount


def check_connection() -> bool:
    """Returns True if the database is reachable."""
    try:
        execute_query("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
