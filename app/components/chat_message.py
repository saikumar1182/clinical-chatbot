"""
chat_message.py — Reusable chat bubble component.
Renders assistant messages with optional source cards and metadata.
"""
import streamlit as st


def render_message(role: str, content: str, sources: list | None = None, meta: str = ""):
    """Render a single chat message with optional source attribution."""
    avatar = "🏥" if role == "assistant" else "👤"
    with st.chat_message(role, avatar=avatar):
        st.markdown(content)
        if sources:
            with st.expander(f"📎 {len(sources)} sources cited"):
                for s in sources:
                    nct = s.get("nct_id", "?")
                    sim = s.get("similarity", 0)
                    status = s.get("status", "")
                    area = s.get("therapeutic_area", "")
                    st.markdown(
                        f"**[{nct}](https://clinicaltrials.gov/study/{nct})**"
                        f"  `{status}` · {area} · sim: {sim:.2f}"
                    )
        if meta:
            st.caption(meta)
