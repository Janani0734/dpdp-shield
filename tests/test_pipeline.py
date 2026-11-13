import pytest

from dpdp_shield.pipeline import PolicyNotFound

QS = [
    "Does this policy cover verifiable parental consent for under-18 users?",
    "What is the data retention period mentioned?",
    "Is there a breach notification clause?",
    "Does the policy mention user rights to delete data?",
    "Is there a grievance redressal contact?",
]


def test_kb_loaded(shield):
    assert shield.kb_chunk_count > 20 and shield.mode == "offline"


def test_bad_policy_report(shield, bad_pdf):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    rep = shield.analyze(doc.id)
    assert rep["summary"]["failed"] >= 3
    row = next(r for r in rep["rows"] if r["violation_type"] == "missing_child_consent")
    assert row["dpdp_ref"].startswith("Section 9") and "parent" in row["fix_suggestion"].lower()
    assert set(rep["rows"][0]) >= {"section", "status", "dpdp_ref", "fix_suggestion"}


def test_good_policy_report(shield, good_pdf):
    rep = shield.analyze(shield.ingest_pdf(good_pdf, "good.pdf").id)
    assert rep["summary"]["failed"] <= 1


@pytest.mark.parametrize("q", QS)
def test_query_shape_citations_latency(shield, bad_pdf, q):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    r = shield.ask(doc.id, q)
    assert set(r) >= {"answer", "citations", "violations", "confidence"}
    assert r["answer"] and 0 <= r["confidence"] <= 1 and r["latency_ms"] < 5000
    assert any(c["scope"] == "dpdp" and c["section"].startswith(("Section", "Rule")) for c in r["citations"])
    assert r["violations"] and {"type", "severity", "fix"} <= set(r["violations"][0])


def test_pass_question_on_good_policy_has_no_violation(shield, good_pdf):
    doc = shield.ingest_pdf(good_pdf, "good.pdf")
    r = shield.ask(doc.id, "What is the data retention period mentioned?")
    assert r["violations"] == [] and "12 months" in r["answer"]


def test_audit_chain_records_everything(shield, bad_pdf):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    shield.analyze(doc.id)
    shield.ask(doc.id, QS[0])
    events = [r["event"] for r in reversed(shield.audit.recent())]
    assert events == ["ingest", "analyze", "query"] and shield.audit.verify()["valid"]


def test_errors(shield, bad_pdf):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    with pytest.raises(ValueError):
        shield.ask(doc.id, "   ")
    with pytest.raises(PolicyNotFound):
        shield.ask("deadbeef0000", "hi")
    with pytest.raises(PolicyNotFound):
        shield.get_policy("../../etc/passwd")


def test_delete_policy(shield, bad_pdf):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    shield.delete_policy(doc.id)
    with pytest.raises(PolicyNotFound):
        shield.get_policy(doc.id)


def test_policy_survives_restart(settings, bad_pdf):
    from dpdp_shield.pipeline import Shield
    pid = Shield(settings).ingest_pdf(bad_pdf, "bad.pdf").id
    assert Shield(settings).analyze(pid)["summary"]["failed"] >= 3


def test_offline_citations_cover_every_cited_section(tmp_path):
    """Section 8 has many chunks; it must not crowd Rule 7 out of the breach answer's citations."""
    import dataclasses
    from dpdp_shield.config import Settings
    from dpdp_shield.pipeline import Shield

    s = dataclasses.replace(Settings.from_env(), data_dir=tmp_path, gemini_api_key="", embeddings_backend="local")
    sh = Shield(s)
    doc = sh.ingest_text("We collect your name and email to deliver orders. " * 5, "t")
    r = sh.ask(doc.id, "Is there a breach notification clause?")
    cited = {(c["source"], c["section"]) for c in r["citations"]}
    assert ("DPDP Rules 2025", "Rule 7") in cited and ("DPDP Act 2023", "Section 8") in cited


def test_query_embedding_is_cached(tmp_path):
    import dataclasses
    from dpdp_shield.config import Settings
    from dpdp_shield.pipeline import Shield

    sh = Shield(dataclasses.replace(Settings.from_env(), data_dir=tmp_path, gemini_api_key="", embeddings_backend="local"))
    calls = []
    real = sh.embedder.embed_query
    sh.embedder.embed_query = lambda t: (calls.append(t), real(t))[1]
    sh._embed_question("Is there a breach notification clause?")
    sh._embed_question("Is there a breach notification clause?")
    assert len(calls) == 1
