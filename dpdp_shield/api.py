"""FastAPI service. Run: uvicorn dpdp_shield.api:app --reload

Public-demo controls (see docs/API_CONTRACT.md): set DEMO_MODE=true to disable uploads server-side,
require `policy_id` on /audit and rate-limit the endpoints that cost compute/LLM calls.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import ROOT, Settings
from .ingestion import PolicyIngestError
from .pipeline import PolicyNotFound, ServiceError, Shield

app = FastAPI(title="DPDP-Shield API", version="1.1.0", description="Audit privacy policies against India's DPDP Act 2023. Not legal advice.")

# Explicit allowlist only (no wildcard, no credentials): the Angular dev server and whatever CORS_ORIGINS lists.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(Settings.from_env().cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Fixed allowlist: the id sent by a client is only ever a dictionary key, never part of a file path.
SAMPLE_DIR = ROOT / "samples"
SAMPLES = {
    "bad_policy": {
        "title": "Sample A - many elements missing",
        "description": "Fictional delivery-app policy written to omit many of the elements the checks look for.",
        "file": "bad_policy.pdf",
    },
    "good_policy": {
        "title": "Sample B - all keyword checks present",
        "description": "Fictional policy that mentions every element the 14 keyword checks look for. "
        "This is not a finding that any policy is legally compliant.",
        "file": "good_policy.pdf",
    },
}


_SHIELD: Shield | None = None
_SHIELD_LOCK = threading.Lock()


def shield() -> Shield:
    """Process-wide singleton. Built under a lock: browsers fire /health and /config together on page load, and
    creating two Chroma PersistentClients at once fails ("Could not connect to tenant default_tenant")."""
    global _SHIELD
    if _SHIELD is None:
        with _SHIELD_LOCK:
            if _SHIELD is None:
                _SHIELD = Shield()
    return _SHIELD


class QueryIn(BaseModel):
    policy_id: str
    question: str = Field(min_length=1, max_length=1000)


# ----------------------------------------------------------------------------- abuse control
class SlidingWindowLimiter:
    """In-memory, per-process limiter. Keyed by client address, so behind a reverse proxy it needs the
    proxy to pass the real client IP (otherwise all visitors share one bucket). Documented limitation."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client, shield().settings.rate_limit_per_min):
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")


def _guard(fn, *a):
    try:
        return fn(*a)
    except PolicyNotFound:
        raise HTTPException(404, "Unknown policy_id. Upload the policy first.")
    except PolicyIngestError as exc:
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except ServiceError as exc:
        raise HTTPException(503, str(exc))


def _upload_response(doc) -> dict:
    return {"policy_id": doc.id, "name": doc.name, "pages": len(doc.pages), "chunks": doc.chunk_count}


# ----------------------------------------------------------------------------- routes
@app.get("/health")
def health():
    s = shield()
    return {"status": "ok", "mode": s.mode, "embeddings": s.embedder.name, "kb_chunks": s.kb_chunk_count, "warnings": s.warnings}


@app.get("/config")
def config():
    """Public, non-secret capabilities and limits so a client does not have to hard-code them."""
    st = shield().settings
    return {
        "demo_mode": st.demo_mode,
        "uploads_enabled": not st.demo_mode,
        "max_pdf_pages": st.max_pdf_pages,
        "max_pdf_mb": st.max_pdf_mb,
        "min_text_chars": 20,
        "max_text_chars": st.max_text_chars,
        "max_question_chars": st.max_question_chars,
        "rate_limit_per_min": st.rate_limit_per_min,
    }


@app.get("/samples")
def list_samples():
    return [
        {"id": sid, "title": m["title"], "description": m["description"], "available": (SAMPLE_DIR / m["file"]).exists()}
        for sid, m in SAMPLES.items()
    ]


@app.post("/samples/{sample_id}/load", dependencies=[Depends(rate_limit)])
def load_sample(sample_id: str):
    meta = SAMPLES.get(sample_id)
    path = (SAMPLE_DIR / meta["file"]) if meta else None
    if not meta or not path.exists():
        raise HTTPException(404, "Unknown sample.")
    return _upload_response(_guard(shield().ingest_pdf, path.read_bytes(), meta["file"]))


@app.post("/policies", dependencies=[Depends(rate_limit)])
def upload_policy(file: UploadFile | None = File(None), text: str | None = Form(None)):
    """Upload a PDF (multipart `file`) or paste text (form field `text`). Disabled when DEMO_MODE is on."""
    s = shield()
    if s.settings.demo_mode:
        raise HTTPException(403, "Uploads are disabled on this server. Load one of the bundled samples instead.")
    if file is not None:
        limit = s.settings.max_pdf_mb * 1024 * 1024
        data = file.file.read(limit + 1)  # bounded read: never buffer an arbitrarily large upload
        doc = _guard(s.ingest_pdf, data, file.filename or "policy.pdf")
    elif text:
        doc = _guard(s.ingest_text, text)
    else:
        raise HTTPException(422, "Provide a PDF `file` or `text`.")
    return _upload_response(doc)


@app.post("/policies/{policy_id}/analyze", dependencies=[Depends(rate_limit)])
def analyze(policy_id: str):
    return _guard(shield().analyze, policy_id)


@app.delete("/policies/{policy_id}")
def delete_policy(policy_id: str):
    shield().delete_policy(policy_id)
    return {"deleted": policy_id}


@app.post("/query", dependencies=[Depends(rate_limit)])
def query(body: QueryIn):
    return _guard(shield().ask, body.policy_id, body.question)


@app.get("/audit")
def audit(limit: int = 50, policy_id: str | None = None):
    """Recent audit rows. In DEMO_MODE `policy_id` is required and only that policy's rows are returned."""
    s = shield()
    if s.settings.demo_mode and not policy_id:
        raise HTTPException(400, "policy_id is required on this server.")
    return s.audit.recent(max(1, min(limit, 500)), policy_id or None)


@app.get("/audit/verify")
def verify():
    """Chain-integrity check over the whole log. Returns aggregates only, never record contents."""
    return shield().audit.verify()
