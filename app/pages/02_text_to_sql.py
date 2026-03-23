"""Page 2: Text-to-SQL Explorer — Natural language → SQL → results table."""
import streamlit as st
import pandas as pd
from src.llm.text_to_sql import run_text_to_sql
from src.db.connection import execute_query

st.title("🗄️ Text-to-SQL Explorer")
st.caption(
    "Ask aggregation questions in plain English. "
    "The AI converts them to PostgreSQL and runs them against the Gold layer."
)

# ── Example queries ──────────────────────────────────────────
with st.expander("💡 Example questions", expanded=True):
    examples = [
        "How many Phase 3 trials are currently recruiting?",
        "List all completed diabetes trials with more than 1000 participants",
        "What are the top 10 sponsors by number of trials?",
        "Show me all cardiovascular trials started after 2020",
        "Count trials by therapeutic area",
        "What percentage of trials are in Phase 3?",
    ]
    cols = st.columns(3)
    for i, ex in enumerate(examples):
        if cols[i % 3].button(ex, key=f"sql_ex_{i}"):
            st.session_state["sql_prefill"] = ex

# ── Input ─────────────────────────────────────────────────────
prefill = st.session_state.pop("sql_prefill", "")
question = st.text_input(
    "Your question:",
    value=prefill,
    placeholder="How many Phase 3 recruiting trials are there?",
)

col_run, col_clear = st.columns([1, 5])
run = col_run.button("▶ Run", type="primary")
col_clear.button("Clear", on_click=lambda: st.session_state.pop("sql_result", None))

if run and question.strip():
    with st.spinner("Generating and executing SQL..."):
        result_str, sql_query = run_text_to_sql(question)

    st.session_state["sql_result"] = {
        "question": question,
        "sql": sql_query,
        "result": result_str,
    }

# ── Results ───────────────────────────────────────────────────
if "sql_result" in st.session_state:
    res = st.session_state["sql_result"]

    st.subheader("Generated SQL")
    st.code(res["sql"], language="sql")

    st.subheader("Results")
    try:
        import ast
        rows = ast.literal_eval(res["result"]) if res["result"].startswith("[") else []
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"{len(df)} rows returned")

            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                "⬇️ Download CSV",
                data=csv,
                file_name="clinical_trials_query.csv",
                mime="text/csv",
            )
        else:
            st.info(res["result"])
    except Exception:
        st.text(res["result"])

# ── Schema reference ─────────────────────────────────────────
with st.expander("📐 Schema reference — gold.trials_enriched"):
    schema = execute_query("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'gold' AND table_name = 'trials_enriched'
        ORDER BY ordinal_position
    """)
    if schema:
        st.dataframe(pd.DataFrame(schema), use_container_width=True, hide_index=True)
    else:
        st.info("Gold layer not yet populated. Run the Airflow pipeline first.")
