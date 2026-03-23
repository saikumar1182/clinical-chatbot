"""
metrics_bar.py — Top KPI bar shown across all pages.
Displays live counts pulled from the database.
"""
import streamlit as st


def render_metrics_bar():
    """Render a horizontal bar of key database metrics."""
    try:
        from src.db.connection import execute_query
        row = execute_query("""
            SELECT
                (SELECT COUNT(*) FROM gold.trials_enriched)              AS trials,
                (SELECT COUNT(*) FROM gold.trials_enriched WHERE is_active) AS active,
                (SELECT COUNT(DISTINCT nct_id) FROM vectors.trial_chunks) AS vectorised,
                (SELECT COUNT(*) FROM eval.traces)                        AS chat_queries
        """)[0]

        cols = st.columns(4)
        cols[0].metric("📋 Total Trials",    f"{row['trials']:,}")
        cols[1].metric("🟢 Active Trials",   f"{row['active']:,}")
        cols[2].metric("🔢 Vectorised",      f"{row['vectorised']:,}")
        cols[3].metric("💬 Chat Queries",    f"{row['chat_queries']:,}")
    except Exception:
        pass   # Fail silently — metrics bar is non-critical
