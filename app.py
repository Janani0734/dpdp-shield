"""DPDP-Shield Streamlit UI. Run: streamlit run app.py"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dpdp_shield.ingestion import PolicyIngestError
from dpdp_shield.pipeline import PolicyNotFound, ServiceError, Shield

ROOT = Path(__file__).parent
SAMPLES = ROOT / "samples"
EXAMPLES = [
    "Does this policy cover verifiable parental consent for under-18 users?",
    "What is the data retention period mentioned?",
    "Is there a breach notification clause?",
    "Does the policy mention user rights to delete data?",
    "Is there a grievance redressal contact?",
]

st.set_page_config(page_title="DPDP-Shield", page_icon="🛡️", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 2.2rem; max-width: 1250px;}
      .ds-badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.75rem; font-weight:600;
                 background:rgba(120,120,120,.15); margin-right:6px;}
      .ds-sev-high {color:#c0392b; font-weight:700;} .ds-sev-medium {color:#d68910; font-weight:700;}
      .ds-sev-low {color:#5d6d7e; font-weight:700;}
      .ds-cite {font-size:0.85rem; opacity:.85;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner="Loading knowledge base...")
def get_shield() -> Shield:
    return Shield()


shield = get_shield()
if not getattr(shield, '_warmed', False):
    shield._warmed = True
    shield.prewarm(EXAMPLES)
ss = st.session_state
ss.setdefault("policy_id", None)
ss.setdefault("policy_name", "")
ss.setdefault("report", None)
ss.setdefault("chat", [])


def load_policy(data: bytes | None, name: str, text: str | None = None) -> None:
    """Ingest + analyze. Replaces any previously loaded policy."""
    try:
        with st.spinner("Reading, chunking, embedding and analysing the policy..."):
            doc = shield.ingest_pdf(data, name) if data is not None else shield.ingest_text(text or "", name)
            report = shield.analyze(doc.id)
    except (PolicyIngestError, ServiceError) as exc:
        st.sidebar.error(str(exc))
        return
    if ss.policy_id:
        shield.delete_policy(ss.policy_id)
    ss.policy_id, ss.policy_name, ss.report, ss.chat = doc.id, doc.name, report, []


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("## 🛡️ DPDP-Shield")
    st.caption("Audit a privacy policy against India's DPDP Act 2023.")
    mode_label = f"Gemini ({shield.llm.model})" if shield.llm else "Offline (rule-based)"
    st.markdown(
        f'<span class="ds-badge">LLM: {mode_label}</span><span class="ds-badge">Embeddings: {shield.embedder.name}</span>'
        f'<span class="ds-badge">KB: {shield.kb_chunk_count} chunks</span>',
        unsafe_allow_html=True,
    )
    for w in shield.warnings:
        st.warning(w, icon="⚠️")

    st.markdown("### 1. Provide a policy")
    up = st.file_uploader("Privacy policy PDF (max 50 pages)", type=["pdf"])
    with st.expander("...or paste text"):
        pasted = st.text_area("Policy text", height=160, label_visibility="collapsed")
    if st.button("Analyze Policy", type="primary", width="stretch"):
        if up is not None:
            load_policy(up.getvalue(), up.name)
        elif pasted.strip():
            load_policy(None, "pasted-policy", pasted)
        else:
            st.error("Upload a PDF or paste some text first.")

    st.markdown("### Or try a sample")
    c1, c2 = st.columns(2)
    if c1.button("Bad policy", width="stretch"):
        load_policy((SAMPLES / "bad_policy.pdf").read_bytes(), "bad_policy.pdf")
    if c2.button("Good policy", width="stretch"):
        load_policy((SAMPLES / "good_policy.pdf").read_bytes(), "good_policy.pdf")
    if ss.policy_id:
        st.success(f"Loaded: {ss.policy_name}")

# ------------------------------------------------------------------ main: chat
st.title("Privacy policy compliance auditor")
st.caption("Ask questions about your policy. Answers cite the DPDP Act / Rules passages they rely on.")

if not ss.policy_id:
    st.info("Upload a policy PDF (or load a sample) in the sidebar, then click **Analyze Policy**.")
else:
    st.markdown("**Try a question:**")
    cols = st.columns(len(EXAMPLES))
    for col, q in zip(cols, EXAMPLES):
        if col.button(q, key=f"ex-{q}", width="stretch"):
            ss.queued_q = q

typed = st.chat_input("Ask about your policy, e.g. Is there a breach notification clause?", disabled=not ss.policy_id)
question = typed or ss.pop("queued_q", None)
if question and ss.policy_id:
    ss.chat.append({"role": "user", "content": question})
    try:
        with st.spinner("Retrieving DPDP clauses and checking your policy..."):
            ss.chat.append({"role": "assistant", "result": shield.ask(ss.policy_id, question)})
    except (ValueError, ServiceError, PolicyNotFound) as exc:
        ss.chat.append({"role": "assistant", "error": str(exc)})


def render_answer(result: dict) -> None:
    st.write(result["answer"])
    tm = result.get("timings")
    detail = f" (embed {tm['embed_ms']} · search {tm['retrieve_ms']} · model {tm['llm_ms']})" if tm else ""
    st.progress(result["confidence"], text=f"Evidence strength (heuristic, not a probability): {result['confidence']:.0%}  |  {result['latency_ms']} ms{detail}  |  mode: {result['mode']}")
    if result["citations"]:
        st.markdown("**Sources**")
        for c in sorted(result["citations"], key=lambda c: c.get("origin") != "official-pdf"):  # official text first
            where = f"{c['source']}" + (f" - {c['section']}" if c.get("section") else "") + (f", p.{c['page']}" if c.get("page") else "")
            tag = " (unofficial summary)" if c.get("origin") not in ("official-pdf", "user-policy") else ""
            st.markdown(f'<div class="ds-cite">• {where}{tag}</div>', unsafe_allow_html=True)
    for v in result["violations"]:
        with st.expander(f"Violation: {v['type']}  ·  severity: {v['severity']}"):
            st.markdown("**Suggested fix**")
            st.code(v["fix"], language=None, wrap_lines=True)
    for w in result["warnings"]:
        st.caption(f"ℹ️ {w}")


for msg in ss.chat:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        elif "error" in msg:
            st.error(msg["error"])
        else:
            render_answer(msg["result"])

# ------------------------------------------------------------------ gap report
if ss.report:
    rep = ss.report
    st.divider()
    st.subheader("Gap report")
    s = rep["summary"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Checks passed", f"{s['passed']} / {s['total_checks']}")
    m2.metric("Gaps found", s["failed"] + s["llm_extra_gaps"])
    m3.metric("High severity", s["by_severity"]["high"])
    m4.metric("Highest penalty ceiling", f"₹{s['highest_penalty_ceiling_crore']} crore" if s["highest_penalty_ceiling_crore"] else "-")
    st.caption(s["note"])
    weak = sum(1 for r in rep["rows"] if r.get("review_note"))
    if weak:
        st.caption(f"⚠️ {weak} of the passed checks were flagged by Gemini as having weak evidence (see notes below the fix text). Treat them as needing review.")
    for w in rep["warnings"]:
        st.caption(f"ℹ️ {w}")
    if shield.llm and any(w.startswith("Gemini review skipped") for w in rep["warnings"]):
        if st.button("↻ Retry Gemini review"):
            with st.spinner("Asking Gemini again (can take up to a minute)..."):
                ss.report = shield.analyze(ss.policy_id)
            st.rerun()

    df = pd.DataFrame(
        [
            {
                "Section": r["section"],
                "Status": ("⚠️ Weak pass" if r.get("review_note") else "✅ Pass") if r["status"] == "pass" else "❌ Fail",
                "Severity": r["severity"].title(),
                "DPDP reference": r["dpdp_ref"],
                "Evidence (page)": (f"p.{r['evidence']['page']}: " if r["evidence"]["page"] else "") + r["evidence"]["snippet"][:110],
                "Penalty ceiling": r["penalty_exposure"],
            }
            for r in rep["rows"]
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True)

    fails = [r for r in rep["rows"] if r["status"] == "fail"]
    if fails:
        st.subheader("Suggested fix text")
        for r in fails:
            with st.expander(f"{r['section']}  ·  {r['severity'].title()}  ·  {r['dpdp_ref']}"):
                st.caption(r["requirement"])
                st.code(r["fix_suggestion"], language=None, wrap_lines=True)
                st.caption(f"Fix source: {r['fix_source']}")
    for r in rep["rows"]:
        if r.get("review_note"):
            st.warning(f"{r['section']}: Gemini thinks the evidence may be weak - {r['review_note']}")

# ------------------------------------------------------------------ audit trail + footer
st.divider()
with st.expander("Audit trail (SHA-256 hash chain)"):
    if st.button("Verify chain integrity"):
        v = shield.audit.verify()
        (st.success if v["valid"] else st.error)(
            f"Chain valid: {v['rows']} rows. Head hash: {v['head_hash'][:16]}..." if v["valid"] else f"Chain BROKEN at row {v['broken_at_id']}: {v['reason']}"
        )
    rows = shield.audit.recent(50)
    if rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "#": r["id"],
                        "Time (UTC)": r["timestamp"][:19],
                        "Event": r["event"],
                        "Query": r["user_query"][:70],
                        "Violations": r["violation_count"],
                        "prev_hash": r["prev_hash"][:10] + "...",
                        "row_hash": r["row_hash"][:10] + "...",
                    }
                    for r in rows
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("No events yet.")

st.caption("⚖️ Disclaimer: DPDP-Shield is an automated aid and is not legal advice. Verify findings with qualified counsel.")
