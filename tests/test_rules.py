from pathlib import Path

from dpdp_shield.rules import extract_durations, relevant_findings, run_checks

S = Path(__file__).resolve().parent.parent / "samples"


def findings(name):
    return run_checks([(1, (S / name).read_text())])


def failed(name):
    return {f.id for f in findings(name) if f.status == "fail"}


def test_bad_policy_flags_at_least_three_and_the_core_five():
    f = failed("bad_policy.txt")
    assert len(f) >= 3
    assert {"missing_child_consent", "missing_retention_period", "missing_breach_notification",
            "missing_erasure_right", "missing_grievance_redressal"} <= f


def test_good_policy_flags_at_most_one():
    assert len(failed("good_policy.txt")) <= 1


def test_vague_retention_is_not_accepted():
    f = run_checks([(1, "We keep your information for as long as necessary for our business needs.")])
    assert next(x for x in f if x.id == "missing_retention_period").status == "fail"


def test_parental_consent_without_verifiable_fails():
    f = run_checks([(1, "Children under 18 need their parent to agree. We obtain parental consent.")])
    assert next(x for x in f if x.id == "missing_child_consent").status == "fail"


def test_evidence_page_is_reported():
    f = run_checks([(1, "Intro text only."), (2, "If a personal data breach occurs we will inform each affected user without delay.")])
    breach = next(x for x in f if x.id == "missing_breach_notification")
    assert breach.status == "pass" and breach.evidence_page == 2


def test_extract_durations():
    assert extract_durations("kept for 12 months and 3 years") == ["12 months", "3 years"]


def test_question_topic_mapping():
    fs = findings("bad_policy.txt")
    cases = {
        "Does this policy cover verifiable parental consent for under-18 users?": "missing_child_consent",
        "What is the data retention period mentioned?": "missing_retention_period",
        "Is there a breach notification clause?": "missing_breach_notification",
        "Does the policy mention user rights to delete data?": "missing_erasure_right",
        "Is there a grievance redressal contact?": "missing_grievance_redressal",
    }
    for q, expected in cases.items():
        assert [f.id for f in relevant_findings(q, fs)] == [expected], q
    assert relevant_findings("Tell me a joke", fs) == []
