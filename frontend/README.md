# DPDP-Shield web (Angular)

Frontend for the DPDP-Shield FastAPI backend: pick a bundled sample (or, where the server allows it, your own
policy), run the checks, review **potential gaps**, ask questions with citations, and verify the audit chain.
Angular 22 (standalone components, signals, strict TypeScript), Angular Material + custom SCSS, Vitest, Playwright.
The API contract the UI is built against is in [`../docs/API_CONTRACT.md`](../docs/API_CONTRACT.md).

## Run locally
```bash
# terminal 1 - backend (repo root)
pip install -r requirements.txt
uvicorn dpdp_shield.api:app --port 8000          # add GEMINI_API_KEY to .env for Gemini; works offline without it

# terminal 2 - frontend
cd frontend && npm ci && npm start               # http://localhost:4200, /api is proxied to 127.0.0.1:8000
```
The Gemini key lives only in the backend `.env`. The frontend never sees it.

## Configuration
* `public/config.json` -> `{"apiBaseUrl": "/api"}`; read at startup, so a deployed build can be pointed at another API without rebuilding. In dev `/api` is proxied (`proxy.conf.json`).
* Backend (see `../.env.example`): `DEMO_MODE`, `CORS_ORIGINS`, `RATE_LIMIT_PER_MIN`, `MAX_TEXT_CHARS`. If the frontend is served from a different origin than the API, set `apiBaseUrl` to the API URL **and** add the frontend origin to `CORS_ORIGINS`.
* The UI reads upload availability and size limits from `GET /config`; nothing is hard-coded.

## Tests
```bash
npm test                    # unit + service/HTTP tests (Vitest, explicit HttpTestingController mocks)
npm run test:e2e:mocked     # Playwright against intercepted (mock) API responses: UI behaviour + axe accessibility scan
npm run test:e2e:real       # Playwright against a real FastAPI process: DEMO_MODE, no Gemini key, local embeddings
```
Playwright starts `ng serve` and the backend itself. If its pinned Chromium is not installed, run `npx playwright install chromium`,
or point `PW_CHROMIUM_PATH` at an existing Chromium binary.
Backend tests: from the repo root, `pytest`.

**What is and is not tested.** Mocked tests prove the UI handles the response shapes and failure states; they say nothing about the backend.
The real-backend tests exercise the true API in offline mode only. **Live Gemini behaviour is not covered by any automated test here**; check it manually
by running the backend with a key and watching the mode banner, `fix_source` and `warnings` on reports and answers.

## Build and deploy
```bash
npm run build               # static files in dist/dpdp-shield-web/browser
```
Serve those files from any static host and route unknown paths to `index.html`. For a **public demo**: run the API with `DEMO_MODE=true`
(uploads are refused by the server with 403, not merely hidden), set `CORS_ORIGINS` to the exact frontend origin, put the API behind HTTPS,
and if it is behind a reverse proxy make sure the client IP is forwarded correctly (the rate limiter keys on the connecting host).

## Behaviour worth knowing
* Nothing is analysed or asked automatically. Uploads, analysis and questions are never retried by the app (they write audit rows and may spend model quota). "Stop waiting" only stops the browser waiting; the server may still finish.
* Findings are "potential gaps", never legal findings; no sample or policy is labelled "compliant". Deterministic rule results and AI-suggested gaps are shown separately and filterable.
* Mode comes from the backend: offline, Gemini configured, Gemini review skipped / answer fallback (from `warnings`/`mode`).
* Chat citations show source, section/rule, page and whether the source is official or an unofficial summary. The backend returns no retrieved passage text for answers, so none is shown.

## Known limitations
* No authentication or per-user isolation: the 12-character `policy_id` is the only capability. Do not enable arbitrary uploads on a shared public server without adding auth, per-user storage and retention.
* Audit entries keep question text and cannot be deleted without breaking the hash chain; deleting a policy leaves its audit rows. `/audit/verify` returns aggregates only and detects edits/deletions, not a full rebuild by someone with write access to the database.
* Reports are not stored server-side; they live in browser memory and are lost on reload (as is the policy list). Re-running analysis repeats the model call.
* The rate limiter is in-memory and per process.
* Accessibility: automated axe scans pass on the five pages (WCAG 2.x A/AA rule set); that is not a substitute for manual screen-reader and keyboard testing, which has not been done.
