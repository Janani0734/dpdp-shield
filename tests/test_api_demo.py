"""Backend changes made for the Angular frontend: CORS, /config, samples, demo mode, audit scoping, abuse controls."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from dpdp_shield import api
from dpdp_shield.config import Settings


@pytest.fixture()
def make_client(shield, monkeypatch):
    def _make(**overrides):
        shield.settings = dataclasses.replace(shield.settings, **overrides)
        monkeypatch.setattr(api, "shield", lambda: shield)
        api.limiter.reset()
        return TestClient(api.app)

    return _make


def test_cors_allows_only_listed_origins(make_client):
    c = make_client()
    ok = c.options("/health", headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:4200"
    bad = c.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
    assert "access-control-allow-credentials" not in ok.headers


def test_cors_origins_parsed_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example/, https://b.example")
    assert Settings.from_env().cors_origins == ("https://a.example", "https://b.example")


def test_config_reports_limits_and_flags(make_client):
    cfg = make_client().get("/config").json()
    assert cfg["uploads_enabled"] is True and cfg["demo_mode"] is False
    assert cfg["max_pdf_mb"] == 20 and cfg["max_pdf_pages"] == 50 and cfg["max_question_chars"] == 1000
    assert "gemini_api_key" not in str(cfg).lower()
    cfg = make_client(demo_mode=True).get("/config").json()
    assert cfg["uploads_enabled"] is False and cfg["demo_mode"] is True


def test_samples_list_and_load_run_end_to_end(make_client):
    c = make_client()
    items = c.get("/samples").json()
    assert {i["id"] for i in items} == {"bad_policy", "good_policy"} and all(i["available"] for i in items)
    assert "compliant" not in " ".join(i["title"].lower() for i in items)
    up = c.post("/samples/bad_policy/load")
    assert up.status_code == 200 and up.json()["pages"] >= 1
    rep = c.post(f"/policies/{up.json()['policy_id']}/analyze").json()
    assert rep["summary"]["failed"] >= 3


def test_sample_id_is_never_a_path(make_client):
    c = make_client()
    assert c.post("/samples/..%2F..%2F.env/load").status_code == 404
    assert c.post("/samples/unknown/load").status_code == 404


def test_demo_mode_blocks_uploads_server_side_but_not_samples(make_client, bad_pdf):
    c = make_client(demo_mode=True)
    assert c.post("/policies", files={"file": ("a.pdf", bad_pdf, "application/pdf")}).status_code == 403
    assert c.post("/policies", data={"text": "We collect your name for delivery. " * 3}).status_code == 403
    assert c.post("/samples/good_policy/load").status_code == 200


def test_audit_is_scoped_in_demo_mode(make_client):
    c = make_client(demo_mode=True)
    a = c.post("/samples/bad_policy/load").json()["policy_id"]
    b = c.post("/samples/good_policy/load").json()["policy_id"]
    c.post("/query", json={"policy_id": a, "question": "SECRET-QUESTION-A breach?"})
    assert c.get("/audit").status_code == 400  # no policy_id -> nothing is listed
    rows_b = c.get("/audit", params={"policy_id": b}).json()
    assert rows_b and all(r["policy_id"] == b for r in rows_b)
    assert "SECRET-QUESTION-A" not in str(rows_b)
    rows_a = c.get("/audit", params={"policy_id": a}).json()
    assert any("SECRET-QUESTION-A" in r["user_query"] for r in rows_a)
    v = c.get("/audit/verify").json()
    assert v["valid"] is True and "user_query" not in v


def test_audit_unscoped_in_local_mode_is_unchanged(make_client):
    c = make_client()
    c.post("/samples/bad_policy/load")
    assert len(c.get("/audit").json()) == 1


def test_rate_limit_applies_to_costly_posts_only(make_client):
    c = make_client(rate_limit_per_min=3)
    codes = [c.post("/samples/bad_policy/load").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert c.get("/health").status_code == 200 and c.get("/config").status_code == 200


def test_text_and_pdf_size_caps(make_client):
    c = make_client(max_text_chars=100)
    r = c.post("/policies", data={"text": "x" * 101})
    assert r.status_code == 400 and "100" in r.json()["detail"]
    c = make_client(max_pdf_mb=0)
    big = b"%PDF-1.4\n" + b"0" * 5000
    r = c.post("/policies", files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 400 and "larger" in r.json()["detail"]


def test_shield_singleton_is_built_once_under_concurrent_first_calls(monkeypatch):
    """Regression: /health and /config arrive together on page load; two Shield() builds at once broke Chroma."""
    import threading
    import time

    built = []

    class Slow:
        def __init__(self):
            built.append(1)
            time.sleep(0.2)

    monkeypatch.setattr(api, "Shield", Slow)
    monkeypatch.setattr(api, "_SHIELD", None)
    results = []
    threads = [threading.Thread(target=lambda: results.append(api.shield())) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(built) == 1
    assert len({id(r) for r in results}) == 1
