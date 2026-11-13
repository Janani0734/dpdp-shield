"""SHA-256 hash-chained audit trail (SQLite).

row_hash = SHA256(canonical JSON of the row's fields, including prev_hash)
prev_hash = previous row's row_hash (GENESIS for the first row)

Tamper evidence: editing or deleting any row breaks every later link. Caveat: someone with write
access to the whole file can rebuild the entire chain, so anchor `head_hash` somewhere you trust
(e.g. print it in CI logs or email it) if you need stronger guarantees.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64
_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    user_query TEXT NOT NULL,
    answer_summary TEXT NOT NULL,
    violation_count INTEGER NOT NULL,
    prev_hash TEXT NOT NULL,
    row_hash TEXT NOT NULL
)
"""
_FIELDS = ("timestamp", "event", "policy_id", "user_query", "answer_summary", "violation_count", "prev_hash")


def compute_hash(payload: dict) -> str:
    canonical = json.dumps({k: payload[k] for k in _FIELDS}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        return con

    def append(self, event: str, policy_id: str, user_query: str, answer_summary: str, violation_count: int) -> dict:
        with _LOCK:
            con = self._connect()
            try:
                con.execute("BEGIN IMMEDIATE")
                last = con.execute("SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
                payload = {
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "event": event,
                    "policy_id": policy_id,
                    "user_query": user_query,
                    "answer_summary": answer_summary[:500],
                    "violation_count": int(violation_count),
                    "prev_hash": last["row_hash"] if last else GENESIS,
                }
                payload["row_hash"] = compute_hash(payload)
                cur = con.execute(
                    "INSERT INTO audit_log (timestamp,event,policy_id,user_query,answer_summary,violation_count,prev_hash,row_hash) "
                    "VALUES (:timestamp,:event,:policy_id,:user_query,:answer_summary,:violation_count,:prev_hash,:row_hash)",
                    payload,
                )
                con.execute("COMMIT")
                payload["id"] = cur.lastrowid
                return payload
            except Exception:
                con.execute("ROLLBACK")
                raise
            finally:
                con.close()

    def recent(self, limit: int = 50, policy_id: str | None = None) -> list[dict]:
        con = self._connect()
        try:
            if policy_id is None:
                rows = con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM audit_log WHERE policy_id = ? ORDER BY id DESC LIMIT ?", (policy_id, limit)
                ).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]

    def verify(self) -> dict:
        con = self._connect()
        try:
            rows = con.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
        finally:
            con.close()
        prev = GENESIS
        for r in rows:
            d = dict(r)
            if d["prev_hash"] != prev:
                return {"valid": False, "rows": len(rows), "broken_at_id": d["id"], "reason": "prev_hash does not match previous row (row removed or reordered)", "head_hash": prev}
            if compute_hash(d) != d["row_hash"]:
                return {"valid": False, "rows": len(rows), "broken_at_id": d["id"], "reason": "row contents do not match row_hash (row was edited)", "head_hash": prev}
            prev = d["row_hash"]
        return {"valid": True, "rows": len(rows), "broken_at_id": None, "reason": "", "head_hash": prev}
