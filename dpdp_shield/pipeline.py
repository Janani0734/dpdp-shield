"""Orchestration: ingest -> retrieve -> (rules + LLM) -> answer / gap report -> audit log."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .audit import AuditLog
from .config import Settings
from .embeddings import GeminiEmbedder, LocalHashEmbedder
from .ingestion import (
    Page,
    PolicyIngestError,
    chunk_pages,
    extract_pdf_pages,
    pages_from_text,
)
from .llm import (
    GeminiLLM,
    LLMError,
    build_query_prompt,
    build_review_prompt,
    citation_from_hit,
    clamp01,
    resolve_citations,
    sanitize_review,
    sanitize_violations,
)
from .report import build_report
from .retrieval import Hit, VectorStore, load_knowledge_base, section_keys
from .rules import CHECKS_BY_ID, Finding, extract_durations, relevant_findings, run_checks

_PID = re.compile(r"^[0-9a-f]{12}$")


class PolicyNotFound(KeyError):
    pass


class ServiceError(RuntimeError):
    """An upstream dependency (embedding API) failed."""


@dataclass
class PolicyDoc:
    id: str
    name: str
    pages: list[Page]
    chunk_count: int
    source_type: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


class Shield:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.data_dir / "policies").mkdir(exist_ok=True)
        self.warnings: list[str] = []
        self.llm = None
        self.embedder = LocalHashEmbedder()
        self._init_backends()
        self.store = VectorStore(self.settings, self.embedder)
        self.kb_chunk_count = self.store.ensure_kb(load_knowledge_base(self.settings))
        self.audit = AuditLog(self.settings.data_dir / "audit.db")
        self.policies: dict[str, PolicyDoc] = {}
        self._findings: dict[str, list[Finding]] = {}
        self._qcache: dict[str, list[float]] = {}

    # ------------------------------------------------------------------ setup
    def _init_backends(self) -> None:
        s = self.settings
        if s.embeddings_backend == "gemini" and not s.gemini_api_key:
            self.warnings.append("EMBEDDINGS_BACKEND=gemini but GEMINI_API_KEY is empty; using local embeddings.")
        if not s.gemini_api_key:
            return
        try:
            from google import genai
            from google.genai import types

            if s.embeddings_backend != "local":
                client = genai.Client(
                    api_key=s.gemini_api_key,
                    http_options=types.HttpOptions(timeout=int(s.llm_timeout_s * 1000)),
                )
                emb = GeminiEmbedder(client, types, s.gemini_embed_model)
                emb.embed_query("connectivity check")
                self.embedder = emb
        except Exception as exc:
            self.warnings.append(f"Gemini embeddings unavailable ({type(exc).__name__}); using local embeddings.")
        try:
            self.llm = GeminiLLM(s)
        except Exception as exc:
            self.warnings.append(f"Gemini LLM unavailable ({type(exc).__name__}); running offline.")

    @property
    def mode(self) -> str:
        return "gemini" if self.llm else "offline"

    # ------------------------------------------------------------------ ingestion
    def ingest_pdf(self, data: bytes, filename: str = "policy.pdf") -> PolicyDoc:
        pages = extract_pdf_pages(data, self.settings.max_pdf_pages, self.settings.max_pdf_mb)
        return self._register(filename, pages, "pdf")

    def ingest_text(self, text: str, name: str = "pasted-policy") -> PolicyDoc:
        if len(text or "") > self.settings.max_text_chars:
            raise PolicyIngestError(f"Pasted text is longer than {self.settings.max_text_chars:,} characters.")
        return self._register(name, pages_from_text(text), "text")

    def _register(self, name: str, pages: list[Page], source_type: str) -> PolicyDoc:
        pid = uuid.uuid4().hex[:12]
        chunks = chunk_pages(pages, pid, name, self.settings.chunk_tokens, self.settings.chunk_overlap_tokens)
        if not chunks:
            raise PolicyIngestError("No text could be extracted from the document.")
        try:
            self.store.add_policy(pid, chunks)
        except Exception as exc:
            self.store.drop_policy(pid)
            raise ServiceError(f"Could not index the policy: {exc}") from exc
        doc = PolicyDoc(pid, name, pages, len(chunks), source_type)
        self.policies[pid] = doc
        self._persist(doc)
        self.audit.append("ingest", pid, f"[INGEST] {name}", f"{len(pages)} page(s), {len(chunks)} chunks indexed", 0)
        return doc

    def _persist(self, doc: PolicyDoc) -> None:
        path = self.settings.data_dir / "policies" / f"{doc.id}.json"
        path.write_text(
            json.dumps(
                {
                    "id": doc.id,
                    "name": doc.name,
                    "source_type": doc.source_type,
                    "created_at": doc.created_at,
                    "chunk_count": doc.chunk_count,
                    "pages": [{"number": p.number, "text": p.text} for p in doc.pages],
                }
            ),
            encoding="utf-8",
        )

    def get_policy(self, policy_id: str) -> PolicyDoc:
        if not policy_id or not _PID.match(policy_id):
            raise PolicyNotFound(policy_id)
        if policy_id in self.policies:
            return self.policies[policy_id]
        path = self.settings.data_dir / "policies" / f"{policy_id}.json"
        if not path.exists():
            raise PolicyNotFound(policy_id)
        d = json.loads(path.read_text(encoding="utf-8"))
        doc = PolicyDoc(d["id"], d["name"], [Page(p["number"], p["text"]) for p in d["pages"]], d["chunk_count"], d["source_type"], d["created_at"])
        self.policies[policy_id] = doc
        return doc

    def delete_policy(self, policy_id: str) -> None:
        if not _PID.match(policy_id or ""):
            return
        self.store.drop_policy(policy_id)
        self.policies.pop(policy_id, None)
        self._findings.pop(policy_id, None)
        (self.settings.data_dir / "policies" / f"{policy_id}.json").unlink(missing_ok=True)

    def _findings_for(self, doc: PolicyDoc) -> list[Finding]:
        if doc.id not in self._findings:
            self._findings[doc.id] = run_checks([(p.number, p.text) for p in doc.pages])
        return self._findings[doc.id]

    # ------------------------------------------------------------------ gap report
    def analyze(self, policy_id: str) -> dict:
        doc = self.get_policy(policy_id)
        findings = self._findings_for(doc)
        warnings = list(self.warnings)
        review = None
        if self.llm:
            failed = [f for f in findings if f.status == "fail"]
            passed = [f for f in findings if f.status == "pass"]
            text = "\n\n".join(f"[Page {p.number}]\n{p.text}" for p in doc.pages)
            if len(text) > self.settings.max_policy_chars_for_llm:
                text = text[: self.settings.max_policy_chars_for_llm]
                warnings.append("Policy was truncated before the Gemini review (very long document).")
            try:
                raw = self.llm.generate_json(build_review_prompt(text, failed, passed), timeout_s=self.settings.review_timeout_s, retries=2)
                review = sanitize_review(raw, {f.id for f in failed}, {f.id for f in passed})
            except LLMError as exc:
                warnings.append(f"Gemini review skipped, using rule-based findings and template fixes: {exc}")
        else:
            warnings.append("Offline mode: rule-based checks and template fixes only (set GEMINI_API_KEY for semantic review).")
        report = build_report(doc, findings, review, self.mode, warnings)
        s = report["summary"]
        self.audit.append("analyze", doc.id, f"[ANALYZE] {doc.name}", f"{s['passed']}/{s['total_checks']} checks passed, {s['failed']} failed", s["failed"])
        return report

    # ------------------------------------------------------------------ Q&A
    def _embed_question(self, question: str) -> list[float]:
        """Query embeddings are cached (a repeated question costs no embedding round-trip)."""
        vec = self._qcache.get(question)
        if vec is None:
            vec = self.embedder.embed_query(question)
            if len(self._qcache) >= 256:
                self._qcache.pop(next(iter(self._qcache)))
            self._qcache[question] = vec
        return vec

    def prewarm(self, questions: list[str]) -> None:
        """Embed the example questions in the background so the first click is fast."""
        import threading

        def work() -> None:
            for q in questions:
                try:
                    self._embed_question(q)
                except Exception:
                    return

        threading.Thread(target=work, daemon=True).start()

    def ask(self, policy_id: str, question: str) -> dict:
        t0 = time.perf_counter()
        question = (question or "").strip()
        if not question:
            raise ValueError("Question is empty.")
        if len(question) > 1000:
            raise ValueError("Question is too long (max 1000 characters).")
        doc = self.get_policy(policy_id)
        findings = self._findings_for(doc)
        relevant = relevant_findings(question, findings)

        t_a = time.perf_counter()
        try:
            qvec = self._embed_question(question)
        except Exception as exc:
            raise ServiceError(f"Embedding service unavailable: {exc}") from exc
        t_b = time.perf_counter()
        k = self.settings.top_k
        kb_hits = self.store.query_kb(qvec, k)
        pol_hits = self.store.query_policy(doc.id, qvec, k)
        pinned = _one_per_section_first(self.store.kb_by_section([key for f in relevant for key in section_keys(f.check.dpdp_ref)]))
        kb_ctx = _merge_hits(pinned, kb_hits)[: k + 3]
        t_c = time.perf_counter()

        scope = relevant if relevant else [f for f in findings if f.status == "fail"]
        rule_violations = [
            {"type": f.id, "severity": f.check.severity, "fix": f.check.fix_template, "source": "rules"}
            for f in scope
            if f.status == "fail"
        ]

        warnings: list[str] = []
        answer, citations, violations, llm_conf = "", [], rule_violations, None
        if self.llm:
            prompt, id_map = build_query_prompt(question, kb_ctx, pol_hits, relevant or findings)
            try:
                raw = self.llm.generate_json(prompt, model=self.settings.gemini_query_model or None, max_tokens=450, retries=1)
                answer = str(raw.get("answer", "")).strip()
                if answer:
                    citations = resolve_citations(raw.get("cited_ids"), id_map)
                    llm_conf = clamp01(raw.get("confidence"))
                    violations = _merge_violations(rule_violations, sanitize_violations(raw.get("violations"), set(CHECKS_BY_ID)), findings)
                else:
                    warnings.append("Gemini returned an empty answer; showing the rule-based answer.")
            except LLMError as exc:
                warnings.append(f"Gemini unavailable for this question ({exc}); showing the rule-based answer.")
        else:
            warnings.append("Offline mode: answer built from rule-based checks and retrieved passages.")
        t_d = time.perf_counter()
        if not answer:
            answer = _offline_answer(relevant, pol_hits)
        if not citations:
            citations = _fallback_citations(pinned, kb_hits, pol_hits, relevant)

        conf = _confidence(llm_conf, bool(relevant), kb_hits, pol_hits)
        result = {
            "answer": answer,
            "citations": citations,
            "violations": violations,
            "confidence": conf,
            "mode": "gemini" if (self.llm and not warnings) else ("gemini-fallback" if self.llm else "offline"),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "timings": {"embed_ms": int((t_b - t_a) * 1000), "retrieve_ms": int((t_c - t_b) * 1000), "llm_ms": int((t_d - t_c) * 1000)},
            "warnings": warnings,
            "policy_id": doc.id,
        }
        entry = self.audit.append("query", doc.id, question, answer.replace("\n", " "), len(violations))
        result["audit"] = {"id": entry["id"], "row_hash": entry["row_hash"]}
        return result


# ---------------------------------------------------------------------- helpers
def _one_per_section_first(hits: list[Hit]) -> list[Hit]:
    """Put the first chunk of every distinct section/rule ahead of extra chunks of the same section,
    so a section with many chunks (e.g. Section 8) cannot crowd Rule 7/9/14 out of the context and citations."""
    seen: set[str] = set()
    firsts, rest = [], []
    for h in sorted(hits, key=lambda h: (h.meta.get("source", ""), h.meta.get("section_key", ""), h.meta.get("page", 0), h.id)):
        key = f"{h.meta.get('source')}|{h.meta.get('section_key')}"
        (rest if key in seen else firsts).append(h)
        seen.add(key)
    return firsts + rest


def _merge_hits(first: list[Hit], second: list[Hit]) -> list[Hit]:
    seen, out = set(), []
    for h in [*first, *second]:
        if h.id not in seen:
            seen.add(h.id)
            out.append(h)
    return out


def _merge_violations(rule_v: list[dict], llm_v: list[dict], findings: list[Finding]) -> list[dict]:
    status = {f.id: f.status for f in findings}
    merged = {v["type"]: dict(v) for v in rule_v}
    for v in llm_v:
        t = v["type"]
        if t in merged:
            if v["fix"]:
                merged[t]["fix"], merged[t]["source"] = v["fix"], "rules+llm"
        elif t in status:
            continue  # rule engine found this requirement present; it has the final say
        else:
            merged[t] = v
    return list(merged.values())


def _offline_answer(relevant: list[Finding], pol_hits: list[Hit]) -> str:
    if relevant:
        lines = []
        for f in relevant:
            if f.status == "pass":
                pg = f" (page {f.evidence_page})" if f.evidence_page else ""
                extra = ""
                if f.id == "missing_retention_period":
                    d = extract_durations(f.evidence_snippet)
                    if d:
                        extra = f" Stated period: {', '.join(d)}."
                lines.append(f'{f.check.section}: addressed{pg}. The policy says: "{f.evidence_snippet}"{extra}')
            else:
                lines.append(
                    f"{f.check.section}: NOT found in the policy. DPDP requires: {f.check.requirement} [{f.check.dpdp_ref}]."
                )
        return "\n".join(lines)
    if pol_hits:
        top = pol_hits[0]
        pg = f" (page {top.page})" if top.page else ""
        return (
            "No specific compliance topic was recognised in the question, so here is the closest passage "
            f'from your policy{pg}: "{top.text[:400].strip()}"'
        )
    return "Nothing relevant was found in the uploaded policy."


def _fallback_citations(pinned: list[Hit], kb_hits: list[Hit], pol_hits: list[Hit], relevant: list[Finding]) -> list[dict]:
    out: list[dict] = []
    kb = pinned[:4] if pinned else [h for h in kb_hits if h.similarity >= 0.1][:2]
    out += [citation_from_hit(h, "dpdp") for h in kb]
    if pol_hits:
        out.append(citation_from_hit(pol_hits[0], "policy"))
    seen, unique = set(), []
    for c in out:  # drop exact repeats (same source, section and page)
        k = (c["source"], c["section"], c["page"])
        if k not in seen:
            seen.add(k)
            unique.append(c)
    return unique


def _confidence(llm_conf: float | None, topic_matched: bool, kb_hits: list[Hit], pol_hits: list[Hit]) -> float:
    """Heuristic, not a calibrated probability: blends retrieval strength, rule-topic match and (if present) the model's own estimate."""
    sims = sorted([h.similarity for h in [*kb_hits, *pol_hits]], reverse=True)[:3]
    retrieval = min(1.0, (sum(sims) / len(sims)) / 0.6) if sims else 0.0
    rule = 1.0 if topic_matched else 0.4
    score = 0.2 * llm_conf + 0.4 * rule + 0.4 * retrieval if llm_conf is not None else 0.55 * rule + 0.45 * retrieval
    return round(min(0.9, max(0.05, score)), 2)
