"""Page 1: RAG Chat — Ask questions about clinical trials."""
import streamlit as st
from src.rag.chain import ask
from src.prompts.registry import list_versions, get_best_version
from src.db.connection import execute_write

st.title("🔬 Clinical Trial Chat")
st.caption("Ask questions in plain English. Every answer is grounded in real trial data with NCT citations.")

# ── Sidebar controls ─────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    versions = list_versions()
    vlabels = {v["version"]: f"{v['version']} (score: {v['score']})" for v in versions}
    best = get_best_version()
    selected_v = st.selectbox(
        "Prompt version",
        list(vlabels.keys()),
        format_func=lambda x: vlabels[x],
        index=list(vlabels.keys()).index(best),
    )
    st.markdown("### 🔽 Filters")
    phase_f = st.multiselect("Phase", [1, 2, 3, 4])
    status_f = st.multiselect("Status", ["RECRUITING", "COMPLETED", "ACTIVE_NOT_RECRUITING"])
    if st.button("🗑 Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# ── Suggested questions ──────────────────────────────────────
with st.expander("💡 Example questions", expanded=False):
    examples = [
        "What is trial NCT04567890 studying?",
        "Explain the eligibility criteria for diabetes Phase 3 trials",
        "What are the main outcomes of completed oncology trials?",
        "How many trials are recruiting for Alzheimer's disease?",
        "Describe the protocol for cardiovascular trials sponsored by Pfizer",
    ]
    cols = st.columns(2)
    for i, ex in enumerate(examples):
        if cols[i % 2].button(ex, key=f"ex_{i}"):
            st.session_state["prefill"] = ex

# ── Chat history ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    avatar = "🏥" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander(f"📎 {len(msg['sources'])} sources cited"):
                for s in msg["sources"]:
                    nct = s.get("nct_id", "?")
                    sim = s.get("similarity", 0)
                    status = s.get("status", "")
                    area = s.get("therapeutic_area", "")
                    st.markdown(
                        f"**[{nct}](https://clinicaltrials.gov/study/{nct})**"
                        f"  `{status}` · {area} · sim: {sim:.2f}"
                    )
        if "meta" in msg:
            st.caption(f"⚡ {msg['meta']}")

# ── Chat input ───────────────────────────────────────────────
prefill = st.session_state.pop("prefill", "")
if question := st.chat_input(prefill or "Ask about clinical trials..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="👤"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🏥"):
        with st.spinner("Searching trial database..."):
            filters = {}
            if phase_f:
                filters["phase"] = phase_f[0] if len(phase_f) == 1 else phase_f
            resp = ask(question, prompt_version=selected_v, filters=filters)

        st.markdown(resp.answer)

        if resp.sources:
            with st.expander(f"📎 {len(resp.sources)} sources cited"):
                for s in resp.sources:
                    nct = s.get("nct_id", "?")
                    sim = s.get("similarity", 0)
                    status = s.get("status", "")
                    area = s.get("therapeutic_area", "")
                    st.markdown(
                        f"**[{nct}](https://clinicaltrials.gov/study/{nct})**"
                        f"  `{status}` · {area} · sim: {sim:.2f}"
                    )

        if resp.sql_query:
            with st.expander("🗄️ SQL executed"):
                st.code(resp.sql_query, language="sql")

        meta_str = f"⚡ {resp.latency_ms}ms · {resp.query_type} · prompt {resp.prompt_version}"
        st.caption(meta_str)

        c1, c2, _ = st.columns([1, 1, 10])
        if c1.button("👍", key=f"up_{resp.trace_id}"):
            execute_write(
                "UPDATE eval.traces SET user_rating=1 WHERE trace_id=:t",
                {"t": resp.trace_id},
            )
        if c2.button("👎", key=f"dn_{resp.trace_id}"):
            execute_write(
                "UPDATE eval.traces SET user_rating=-1 WHERE trace_id=:t",
                {"t": resp.trace_id},
            )

    st.session_state.messages.append({
        "role": "assistant",
        "content": resp.answer,
        "sources": resp.sources,
        "meta": meta_str,
    })
