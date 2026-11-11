import pytest
from fastapi.testclient import TestClient

from dpdp_shield import api


@pytest.fixture()
def client(shield, monkeypatch):
    monkeypatch.setattr(api, "shield", lambda: shield)
    return TestClient(api.app)


def test_full_flow(client, bad_pdf):
    assert client.get("/health").json()["status"] == "ok"
    up = client.post("/policies", files={"file": ("bad.pdf", bad_pdf, "application/pdf")})
    assert up.status_code == 200
    pid = up.json()["policy_id"]
    assert client.post(f"/policies/{pid}/analyze").json()["summary"]["failed"] >= 3
    r = client.post("/query", json={"policy_id": pid, "question": "Is there a breach notification clause?"})
    assert r.status_code == 200 and r.json()["citations"] and r.json()["violations"]
    assert len(client.get("/audit").json()) == 3
    assert client.get("/audit/verify").json()["valid"] is True


def test_text_upload_and_errors(client):
    assert client.post("/policies", data={"text": "We collect your name for the purpose of delivery. " * 3}).status_code == 200
    assert client.post("/policies", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 400
    assert client.post("/policies").status_code == 422
    assert client.post("/query", json={"policy_id": "deadbeef0000", "question": "hi"}).status_code == 404
    assert client.post("/query", json={"policy_id": "deadbeef0000", "question": ""}).status_code == 422
