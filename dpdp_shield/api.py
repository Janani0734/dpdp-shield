"""FastAPI service. Run: uvicorn dpdp_shield.api:app --reload"""
from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .ingestion import PolicyIngestError
from .pipeline import PolicyNotFound, ServiceError, Shield

app = FastAPI(title="DPDP-Shield API", version="1.0.0", description="Audit privacy policies against India's DPDP Act 2023. Not legal advice.")


@lru_cache(maxsize=1)
def shield() -> Shield:
    return Shield()


class QueryIn(BaseModel):
    policy_id: str
    question: str = Field(min_length=1, max_length=1000)


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


@app.get("/health")
def health():
    s = shield()
    return {"status": "ok", "mode": s.mode, "embeddings": s.embedder.name, "kb_chunks": s.kb_chunk_count, "warnings": s.warnings}


@app.post("/policies")
def upload_policy(file: UploadFile | None = File(None), text: str | None = Form(None)):
    """Upload a PDF (multipart `file`) or paste text (form field `text`)."""
    s = shield()
    if file is not None:
        doc = _guard(s.ingest_pdf, file.file.read(), file.filename or "policy.pdf")
    elif text:
        doc = _guard(s.ingest_text, text)
    else:
        raise HTTPException(422, "Provide a PDF `file` or `text`.")
    return {"policy_id": doc.id, "name": doc.name, "pages": len(doc.pages), "chunks": doc.chunk_count}


@app.post("/policies/{policy_id}/analyze")
def analyze(policy_id: str):
    return _guard(shield().analyze, policy_id)


@app.delete("/policies/{policy_id}")
def delete_policy(policy_id: str):
    shield().delete_policy(policy_id)
    return {"deleted": policy_id}


@app.post("/query")
def query(body: QueryIn):
    return _guard(shield().ask, body.policy_id, body.question)


@app.get("/audit")
def audit(limit: int = 50):
    return shield().audit.recent(max(1, min(limit, 500)))


@app.get("/audit/verify")
def verify():
    return shield().audit.verify()
