"""app/main.py — Streamlit entry point with shared layout."""
import streamlit as st

st.set_page_config(
    page_title="ClinicalChat QA",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .stApp { background-color: #07090f; color: #e2e8f0; }
  .stSidebar { background-color: #0c1018; border-right: 1px solid rgba(99,179,237,.15); }
  .main .block-container { padding-top: 1.5rem; max-width: 1100px; }
  [data-testid="metric-container"] {
    background: #111827;
    border: 1px solid rgba(99,179,237,.15);
    border-radius: 8px;
    padding: 12px;
  }
  .stButton button {
    background: rgba(99,179,237,.1);
    border: 1px solid rgba(99,179,237,.3);
    color: #63b3ed;
  }
</style>
""", unsafe_allow_html=True)


st.markdown("## ClinicalChat QA")
st.markdown("*Clinical trial intelligence platform*")
st.divider()
try:
    from src.db.connection import execute_query
    r = execute_query("SELECT COUNT(*) AS n FROM gold.trials_enriched")
    vc = execute_query("SELECT COUNT(DISTINCT nct_id) AS n FROM vectors.trial_chunks")
    st.success(f"{r[0]['n']:,} trials indexed")
    st.info(f"{vc[0]['n']:,} vectors in pgvector")
except Exception:
    st.error("Database not connected")
