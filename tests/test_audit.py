import sqlite3
import threading

from dpdp_shield.audit import GENESIS, AuditLog


def make(tmp_path, n=5):
    log = AuditLog(tmp_path / "a.db")
    for i in range(n):
        log.append("query", "p1", f"q{i}", f"a{i}", i)
    return log


def test_chain_links_and_verifies(tmp_path):
    log = make(tmp_path)
    rows = list(reversed(log.recent(10)))
    assert rows[0]["prev_hash"] == GENESIS
    assert all(rows[i]["prev_hash"] == rows[i - 1]["row_hash"] for i in range(1, len(rows)))
    assert log.verify()["valid"] is True


def test_empty_log_is_valid(tmp_path):
    assert AuditLog(tmp_path / "a.db").verify() == {"valid": True, "rows": 0, "broken_at_id": None, "reason": "", "head_hash": GENESIS}


def test_edit_is_detected(tmp_path):
    log = make(tmp_path)
    con = sqlite3.connect(log.path)
    con.execute("UPDATE audit_log SET answer_summary='tampered' WHERE id=3")
    con.commit()
    v = log.verify()
    assert v["valid"] is False and v["broken_at_id"] == 3


def test_deleted_row_is_detected(tmp_path):
    log = make(tmp_path)
    con = sqlite3.connect(log.path)
    con.execute("DELETE FROM audit_log WHERE id=2")
    con.commit()
    v = log.verify()
    assert v["valid"] is False and v["broken_at_id"] == 3


def test_concurrent_appends_keep_chain_valid(tmp_path):
    log = AuditLog(tmp_path / "a.db")
    ts = [threading.Thread(target=lambda i=i: [log.append("query", "p", f"t{i}-{j}", "a", 0) for j in range(10)]) for i in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    v = log.verify()
    assert v["valid"] and v["rows"] == 50
