"""Page 3: Analytics Dashboard — Business KPIs from Gold layer."""
import streamlit as st
import pandas as pd
import plotly.express as px
from src.db.connection import execute_query

st.title("📊 Trial Analytics Dashboard")
st.caption("Business intelligence built directly from the Gold layer — same data the chat uses.")

# ── KPI row ──────────────────────────────────────────────────
kpis = execute_query("""
    SELECT
        COUNT(*) AS total_trials,
        COUNT(*) FILTER (WHERE status = 'RECRUITING') AS recruiting,
        COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed,
        COUNT(*) FILTER (WHERE phase_num = 3) AS phase_3,
        ROUND(AVG(enrollment_count)) AS avg_enrollment,
        COUNT(DISTINCT therapeutic_area) AS therapeutic_areas
    FROM gold.trials_enriched
""")[0]

cols = st.columns(6)
metrics = [
    ("📋 Total Trials",         kpis["total_trials"],        None),
    ("🟢 Recruiting",           kpis["recruiting"],           None),
    ("✅ Completed",             kpis["completed"],            None),
    ("🔬 Phase 3",              kpis["phase_3"],              None),
    ("👥 Avg Enrollment",       kpis["avg_enrollment"],       None),
    ("🏥 Therapeutic Areas",    kpis["therapeutic_areas"],    None),
]
for col, (label, val, delta) in zip(cols, metrics):
    col.metric(label, f"{val:,}" if val else "N/A")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Status Distribution")
    rows = execute_query("""
        SELECT status, COUNT(*) AS count
        FROM gold.trials_enriched
        GROUP BY status ORDER BY count DESC LIMIT 8
    """)
    df = pd.DataFrame(rows)
    fig = px.pie(
        df, values="count", names="status", hole=0.4,
        color_discrete_map={
            "COMPLETED": "#68d391", "RECRUITING": "#63b3ed",
            "TERMINATED": "#fc8181", "ACTIVE_NOT_RECRUITING": "#f6ad55",
        },
    )
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94a3b8")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Trials by Phase")
    rows = execute_query("""
        SELECT phase_num, COUNT(*) AS count
        FROM gold.trials_enriched WHERE phase_num IS NOT NULL
        GROUP BY phase_num ORDER BY phase_num
    """)
    df = pd.DataFrame(rows)
    fig = px.bar(df, x="phase_num", y="count", color="count", color_continuous_scale="Blues",
                 labels={"phase_num": "Phase", "count": "Trials"})
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94a3b8")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("📅 Trials Submitted by Month")
rows = execute_query("""
    SELECT DATE_TRUNC('month', submit_date) AS month, COUNT(*) AS trials
    FROM gold.trials_enriched
    WHERE submit_date >= CURRENT_DATE - INTERVAL '3 years'
    GROUP BY 1 ORDER BY 1
""")
df = pd.DataFrame(rows)
if not df.empty:
    fig = px.area(df, x="month", y="trials", line_shape="spline")
    fig.update_traces(line_color="#63b3ed", fillcolor="rgba(99,179,237,.1)")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94a3b8")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("🏥 Top Therapeutic Areas")
rows = execute_query("""
    SELECT therapeutic_area, COUNT(*) AS count
    FROM gold.trials_enriched
    WHERE therapeutic_area IS NOT NULL
    GROUP BY therapeutic_area ORDER BY count DESC LIMIT 10
""")
df = pd.DataFrame(rows)
if not df.empty:
    fig = px.bar(df, x="count", y="therapeutic_area", orientation="h", color="count",
                 color_continuous_scale="Teal")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font_color="#94a3b8", yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)
