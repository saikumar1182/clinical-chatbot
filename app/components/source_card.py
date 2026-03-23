"""
source_card.py — Render a single NCT ID citation card.
Used in the chat page to show source attribution per answer.
"""
import streamlit as st


def render_source_card(source: dict):
    """Render one source card with NCT link, status badge, and similarity score."""
    nct_id   = source.get("nct_id", "Unknown")
    sim      = source.get("similarity", 0)
    status   = source.get("status", "")
    area     = source.get("therapeutic_area", "")
    sponsor  = source.get("sponsor", "")

    status_colors = {
        "RECRUITING":              "#68d391",
        "COMPLETED":               "#63b3ed",
        "ACTIVE_NOT_RECRUITING":   "#f6ad55",
        "TERMINATED":              "#fc8181",
    }
    color = status_colors.get(status, "#94a3b8")

    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(99,179,237,.2);
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 8px;
            background: rgba(17,24,39,.6);
        ">
            <a href="https://clinicaltrials.gov/study/{nct_id}" target="_blank"
               style="color:#63b3ed; font-weight:600; text-decoration:none;">
                {nct_id}
            </a>
            <span style="
                background: {color}22;
                color: {color};
                border: 1px solid {color}44;
                border-radius: 12px;
                font-size: 10px;
                padding: 1px 8px;
                margin-left: 8px;
            ">{status}</span>
            <span style="float:right; font-size:11px; color:#94a3b8;">
                sim: {sim:.2f}
            </span>
            <br/>
            <span style="font-size:12px; color:#94a3b8;">{area}</span>
            {f'<span style="font-size:11px; color:#64748b;"> · {sponsor}</span>' if sponsor else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )
