"""Gemini path tested with a fake model (no network, no key needed)."""
import pytest

from dpdp_shield.llm import LLMError, parse_json, sanitize_review, sanitize_violations


class FakeLLM:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.prompts = payload, error, []

    def generate_json(self, prompt, system=None, timeout_s=None, retries=1, model=None, max_tokens=4096):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.payload


def test_parse_json_variants():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": 2} done') == {"a": 2}
    for bad in ("", "no json here", "[1,2]", '{"a": '):
        with pytest.raises(LLMError):
            parse_json(bad)


def test_citations_come_only_from_retrieved_context(shield, bad_pdf):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    shield.llm = FakeLLM({
        "answer": "No verifiable parental consent clause was found.",
        "cited_ids": ["K1", "P1", "K99", "Section 999"],
        "violations": [{"type": "missing_child_consent", "severity": "HIGH", "fix": "LLM clause"},
                       {"type": "missing_security_safeguards", "severity": "high", "fix": "should be dropped: rules say present"},
                       {"type": "Weird Type!", "severity": "bogus", "fix": "x"}],
        "confidence": 0.9,
    })
    r = shield.ask(doc.id, "Does this policy cover verifiable parental consent for under-18 users?")
    assert r["mode"] == "gemini" and r["answer"].startswith("No verifiable")
    assert len(r["citations"]) == 2  # K1 + P1 only; fabricated ids dropped
    assert all(c["section"] != "Section 999" for c in r["citations"])
    types = {v["type"]: v for v in r["violations"]}
    assert types["missing_child_consent"]["fix"] == "LLM clause" and types["missing_child_consent"]["source"] == "rules+llm"
    assert "missing_security_safeguards" not in types
    assert types["weird_type"]["severity"] == "medium" and types["weird_type"]["source"] == "llm"
    assert "Compare the user's privacy policy" in shield.llm.prompts[0] or "DPDP" in shield.llm.prompts[0]


def test_llm_failure_falls_back_to_rules(shield, bad_pdf):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    shield.llm = FakeLLM(error=LLMError("quota exceeded"))
    r = shield.ask(doc.id, "Is there a breach notification clause?")
    assert r["mode"] == "gemini-fallback" and "NOT found" in r["answer"] and any("quota" in w for w in r["warnings"])
    assert r["violations"][0]["type"] == "missing_breach_notification"


def test_analyze_uses_llm_fixes_and_validates(shield, bad_pdf):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    shield.llm = FakeLLM({
        "fixes": {"missing_child_consent": "Tailored child clause", "not_a_real_id": "ignored"},
        "extra_gaps": [{"section": "Marketing", "issue": "Marketing consent bundled", "severity": "high", "fix": "Separate opt-in"}, {"issue": ""}],
        "weak_passes": [{"id": "missing_security_safeguards", "reason": "only payments encrypted"}, {"id": "bogus", "reason": "x"}],
    })
    rep = shield.analyze(doc.id)
    child = next(r for r in rep["rows"] if r["violation_type"] == "missing_child_consent")
    assert child["fix_suggestion"] == "Tailored child clause" and child["fix_source"] == "gemini"
    assert rep["summary"]["llm_extra_gaps"] == 1
    assert next(r for r in rep["rows"] if r["section"] == "Security safeguards")["review_note"] == "only payments encrypted"
    assert not any("ignored" == r["fix_suggestion"] for r in rep["rows"])


def test_sanitizers_handle_garbage():
    assert sanitize_review({"fixes": "x", "extra_gaps": "y", "weak_passes": None}, {"a"}, {"b"}) == {"fixes": {}, "extra_gaps": [], "weak_passes": {}}
    assert sanitize_review({"fixes": {"a": 5}, "extra_gaps": [1, None, {"issue": "ok"}], "weak_passes": ["x"]}, {"a"}, {"b"})["fixes"] == {"a": "5"}
    assert sanitize_violations("nope", set()) == []
    assert sanitize_violations([None, 3, {"type": ""}], set()) == []


def _bare_llm(once, fallback=""):
    from dpdp_shield.llm import GeminiLLM
    llm = GeminiLLM.__new__(GeminiLLM)
    llm.model, llm.fallback_model, llm._once = "main", fallback, once
    return llm


def test_transient_errors_are_retried(monkeypatch):
    monkeypatch.setattr("dpdp_shield.llm.time.sleep", lambda s: None)
    calls = []

    def once(model, prompt, system, timeout_s, max_tokens=4096):
        calls.append(model)
        if len(calls) < 3:
            raise LLMError("Gemini request failed: ServerError: 503 UNAVAILABLE high demand")
        return {"ok": 1}

    assert _bare_llm(once).generate_json("p", retries=2) == {"ok": 1} and len(calls) == 3


def test_permanent_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr("dpdp_shield.llm.time.sleep", lambda s: None)
    calls = []

    def once(model, prompt, system, timeout_s, max_tokens=4096):
        calls.append(1)
        raise LLMError("Gemini request failed: ClientError: 404 NOT_FOUND")

    with pytest.raises(LLMError):
        _bare_llm(once).generate_json("p", retries=3)
    assert len(calls) == 1


def test_fallback_model_used_after_retries(monkeypatch):
    monkeypatch.setattr("dpdp_shield.llm.time.sleep", lambda s: None)
    seen = []

    def once(model, prompt, system, timeout_s, max_tokens=4096):
        seen.append(model)
        if model == "main":
            raise LLMError("503 UNAVAILABLE")
        return {"from": model}

    assert _bare_llm(once, fallback="backup").generate_json("p", retries=1) == {"from": "backup"}
    assert seen == ["main", "main", "backup"]


def test_retention_question_keeps_rule_violation_with_gemini(shield, bad_pdf):
    """Regression check: a Gemini answer must not drop the rule engine's violation for the asked topic."""
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    shield.llm = FakeLLM({"answer": "No concrete retention period is stated.", "cited_ids": ["K1"], "violations": [], "confidence": 1.0})
    r = shield.ask(doc.id, "What is the data retention period mentioned?")
    assert [v["type"] for v in r["violations"]] == ["missing_retention_period"]
    assert r["confidence"] <= 0.9 and set(r["timings"]) == {"embed_ms", "retrieve_ms", "llm_ms"}


def test_query_model_and_token_cap_are_passed(shield, bad_pdf):
    doc = shield.ingest_pdf(bad_pdf, "bad.pdf")
    seen = {}

    class Spy(FakeLLM):
        def generate_json(self, prompt, system=None, timeout_s=None, retries=1, model=None, max_tokens=4096):
            seen.update(model=model, max_tokens=max_tokens, retries=retries)
            return {"answer": "ok", "cited_ids": [], "violations": [], "confidence": 0.5}

    import dataclasses
    shield.settings = dataclasses.replace(shield.settings, gemini_query_model="fast-model")
    shield.llm = Spy()
    shield.ask(doc.id, "Is there a breach notification clause?")
    assert seen == {"model": "fast-model", "max_tokens": 450, "retries": 1}
