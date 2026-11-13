# DPDP-Shield API contract (Phase 1 inventory)

Derived by reading `dpdp_shield/api.py`, `pipeline.py`, `report.py`, `audit.py`, `config.py`,
`tests/test_api.py`, and by calling the real FastAPI app with `TestClient` (offline mode) and dumping
the JSON shapes. Nothing below is assumed; items marked **(new)** do not exist yet and are listed under
"Required backend changes".

## 1. Existing endpoints

| Method + path | Request | 200 response | Error responses |
|---|---|---|---|
| `GET /health` | - | `{status, mode, embeddings, kb_chunks, warnings: string[]}` | - |
| `POST /policies` | multipart `file` (PDF) **or** form `text` | `{policy_id, name, pages, chunks}` | 400 `{detail: string}` (bad/oversized/scanned PDF, text too short); 422 `{detail: string}` (neither field); 503 (index failure) |
| `POST /policies/{id}/analyze` | - | **Report** (below) | 404 unknown id; 503 |
| `DELETE /policies/{id}` | - | `{deleted: id}` (also 200 for unknown ids; idempotent) | - |
| `POST /query` | JSON `{policy_id, question (1-1000 chars)}` | **QueryResult** (below) | 404 unknown id; 422 **`detail` is an array** for body validation (empty question) but a string for other 422s; 503 embedding failure |
| `GET /audit?limit=50` | `limit` clamped to 1-500 | `AuditRow[]`, newest first | - |
| `GET /audit/verify` | - | `{valid, rows, broken_at_id: number\|null, reason, head_hash}` | - |

### Report (`POST /policies/{id}/analyze`)
```
{ policy_id, policy_name, generated_at (ISO), mode: "gemini"|"offline",
  summary: { total_checks, passed, failed, llm_extra_gaps,
             by_severity: {high, medium, low}, highest_penalty_ceiling_crore, note },
  rows: Row[], warnings: string[], disclaimer }
Row = { section, status: "pass"|"fail", severity: "high"|"medium"|"low", dpdp_ref,
        violation_type, requirement, evidence: {snippet, page: number|null},
        fix_suggestion, fix_source: "gemini"|"template"|"", penalty_exposure,
        review_note, detected_by: "rules"|"llm" }
```
Facts the UI may rely on (verified in `report.py`):
* `detected_by:"rules"` rows are deterministic regex checks; `detected_by:"llm"` rows are extra gaps
  suggested by the model (their `dpdp_ref` contains "LLM-suggested, verify", `violation_type` is `llm_semantic_gap`).
* A rule `pass` with a non-empty `review_note` is a "weak pass" flagged by the model (advisory only).
* `summary.failed` counts rule failures only; `llm_extra_gaps` is separate. `by_severity` includes both.
* `mode` is `"gemini"` when a key is configured even if the review step failed; in that case a
  `warnings` entry begins "Gemini review skipped" and every `fix_source` is `"template"`.
* `penalty_exposure` is a string ("Up to ₹50 crore (...)"), not a number.

### QueryResult (`POST /query`)
```
{ answer, citations: Citation[], violations: {type, severity, fix, source: "rules"|"rules+llm"|"llm"}[],
  confidence (0-0.9 heuristic), mode: "gemini"|"gemini-fallback"|"offline",
  latency_ms, timings: {embed_ms, retrieve_ms, llm_ms}, warnings: string[], policy_id,
  audit: {id, row_hash} }
Citation = { source, section, title, page: number|null, origin: "official-pdf"|"working-summary"|"project-template"|"user-policy",
             scope: "dpdp"|"policy" }
```
* **The backend does not return retrieved passage text.** The UI must therefore show citation metadata only, never "evidence quotes" for chat answers.
* `page` is the position in the bundled PDF (not a printed Gazette number, though they coincide for the shipped files).
* `origin` other than `official-pdf`/`user-policy` is an unofficial summary and must be labelled as such.
* `mode:"gemini-fallback"` means Gemini is configured but the call failed or was empty; the answer is rule-based; `warnings` explains why.

### AuditRow / verify
`AuditRow = {id, timestamp, event: "ingest"|"analyze"|"query", policy_id, user_query, answer_summary, violation_count, prev_hash, row_hash}`.
`/audit/verify` checks the whole chain and returns only aggregates (no record content). It detects edits/deletions of
rows but not a wholesale rebuild by someone with write access to the SQLite file (see `audit.py` docstring).

### Limits (from `Settings`)
`max_pdf_pages=50`, `max_pdf_mb=20`, question max 1000 chars, text min 20 chars after trimming.
**No maximum for pasted text exists** (gap, see below). Limits are not exposed to clients today.

## 2. Gaps found (what the requested frontend needs that the backend lacks)

| # | Gap | Evidence | Why it matters |
|---|---|---|---|
| G1 | **No CORS middleware** | OPTIONS preflight from `http://localhost:4200` returned no `access-control-allow-origin` | Browser calls from a separately hosted frontend would be blocked; the production origin must be an explicit allowlist. |
| G2 | **No sample endpoints** | Samples are read from `samples/` by Streamlit only | The frontend cannot load "bundled samples" without shipping the PDFs or sending them as uploads (which must be disabled in demo mode). |
| G3 | **No capability/limits endpoint** | `/health` has no limits or upload flag | The UI must "match backend limits" and hide uploads when disabled, without hard-coding numbers. |
| G4 | **`/audit` returns every record from every user**, including free-text questions | `GET /audit` has no filter | Violates "do not expose other users' records" on a shared deployment. |
| G5 | **Uploads cannot be disabled server-side** | `POST /policies` always accepts | A frontend-only restriction is not a control. |
| G6 | **No abuse controls** | no rate limit; pasted text has no size cap; whole upload is read into memory before the size check | `/analyze` and `/query` spend Gemini quota per call. |
| G7 | No auth / user isolation | `policy_id` (12 hex chars) is the only capability | Documented limitation; not solved here. Real multi-user uploads need auth, per-user storage and retention. |
| G8 | Audit rows keep question text and cannot be deleted without breaking the hash chain | `audit.py` | `DELETE /policies/{id}` removes the policy but not its audit rows. Documented limitation. |
| G9 | Reports are not stored or retrievable | `analyze` recomputes (and calls Gemini again) every time | The frontend must cache the last report in memory; "Dashboard" can only show reports analysed in this browser session. |
| G10 | No list-policies endpoint | none | The frontend tracks only the policy ids it created in this session (it cannot list other users' policies, which is intended). |

## 3. Required backend changes (minimal, additive, backwards compatible)

All new behaviour is controlled by settings with defaults that keep today's behaviour for local use
(Streamlit, existing tests). A public deployment must set `DEMO_MODE=true`.

1. **CORS (G1):** `CORSMiddleware` with an explicit allowlist from `CORS_ORIGINS` (default `http://localhost:4200,http://127.0.0.1:4200`); methods GET/POST/DELETE; no credentials; no wildcard.
2. **`GET /config` (G3, new):** `{demo_mode, uploads_enabled, max_pdf_pages, max_pdf_mb, min_text_chars, max_text_chars, max_question_chars, rate_limit_per_min}`.
3. **`GET /samples`, `POST /samples/{sample_id}/load` (G2, new):** fixed allowlist `bad_policy`, `good_policy` mapped server-side to files in `samples/`; the id never becomes a path. Returns the same shape as `POST /policies`.
4. **`DEMO_MODE` (G5):** `POST /policies` returns **403** while keeping samples available. Server-side, independent of the frontend.
5. **Audit scoping (G4):** `GET /audit` accepts `policy_id`; in `DEMO_MODE` it is **required** and only rows for that policy are returned. `/audit/verify` stays global because it returns no records.
6. **Abuse controls (G6):** per-client sliding-window limit (`RATE_LIMIT_PER_MIN`, default 0 = off, 20 when `DEMO_MODE`) on `POST` endpoints that cost compute/LLM; `MAX_TEXT_CHARS` (default 100 000) for pasted text; bounded read of uploads (`max_pdf_mb + 1`).
7. **Not changed:** retrieval, rules, prompts, Gemini logic, Streamlit app, existing response shapes.

## 4. Frontend rules that follow from the contract
* Never auto-retry `POST /policies`, `/analyze`, `/query`, `/samples/*/load` (they write audit rows and may spend LLM quota). GET requests may be retried manually by the user only.
* Handle both `detail: string` and `detail: ValidationError[]`.
* Treat `status:"fail"` as a **potential gap**, never as a legal violation; never label a sample or policy "compliant".
* Show Gemini/offline/fallback state from `mode` + `warnings`, not from assumptions.
