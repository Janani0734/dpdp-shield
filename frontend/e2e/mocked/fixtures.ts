import { Page } from '@playwright/test';

/** EXPLICIT MOCKS: these fixtures replace the backend. Tests using them verify the UI only. */
export const cfg = (over: Record<string, unknown> = {}) => ({
  demo_mode: true, uploads_enabled: false, max_pdf_pages: 50, max_pdf_mb: 20, min_text_chars: 20, max_text_chars: 100000, max_question_chars: 1000, rate_limit_per_min: 20, ...over,
});
export const health = { status: 'ok', mode: 'offline', embeddings: 'local-hash', kb_chunks: 134, warnings: [] };
export const samples = [
  { id: 'bad_policy', title: 'Sample A - many elements missing', description: 'demo', available: true },
  { id: 'good_policy', title: 'Sample B - all keyword checks present', description: 'Not a finding of legal compliance.', available: true },
];
const row = (o: object) => ({ section: 'Notice', status: 'fail', severity: 'high', dpdp_ref: 'DPDP Act s.5', violation_type: 'x', requirement: 'Give notice', evidence: { snippet: '', page: null }, fix_suggestion: 'Add a notice.', fix_source: 'template', penalty_exposure: 'Up to ₹50 crore', review_note: '', detected_by: 'rules', ...o });
export const report = (over: object = {}) => ({
  policy_id: 'aaaaaaaaaaaa', policy_name: 'Sample A - many elements missing', generated_at: '2026-11-12T00:00:00Z', mode: 'offline',
  summary: { total_checks: 3, passed: 1, failed: 2, llm_extra_gaps: 1, by_severity: { high: 2, medium: 1, low: 0 }, highest_penalty_ceiling_crore: 250, note: '' },
  rows: [
    row({ section: 'Notice' }),
    row({ section: 'Security safeguards', severity: 'medium', fix_suggestion: 'Describe safeguards.' }),
    row({ section: 'Retention', status: 'pass', severity: 'low', evidence: { snippet: 'We keep data for 1 year.', page: 2 }, fix_suggestion: '' }),
    row({ section: 'Cross-border', severity: 'medium', detected_by: 'llm', dpdp_ref: 'LLM-suggested, verify', violation_type: 'llm_semantic_gap' }),
  ],
  warnings: [], disclaimer: 'x', ...over,
});
export const query = (over: object = {}) => ({
  answer: 'The policy does not state a breach-notification period.', citations: [{ source: 'DPDP Rules 2025', section: 'Rule 7', title: 'Breach intimation', page: 12, origin: 'official-pdf', scope: 'dpdp' }],
  violations: [], confidence: 0.6, mode: 'offline', latency_ms: 40, timings: { embed_ms: 1, retrieve_ms: 2, llm_ms: 0 }, warnings: [], policy_id: 'aaaaaaaaaaaa', audit: { id: 1, row_hash: 'h' }, ...over,
});

export async function mockApi(page: Page, opts: { config?: object; analyze?: () => object | number; query?: () => object | number; verify?: object } = {}) {
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url());
    const p = u.pathname.replace(/^\/api/, '');
    const m = route.request().method();
    const ok = (b: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) });
    if (p === '/health') return ok(health);
    if (p === '/config') return ok(cfg(opts.config));
    if (p === '/samples') return ok(samples);
    if (p.startsWith('/samples/') && m === 'POST') return ok({ policy_id: 'aaaaaaaaaaaa', name: samples[0]!.title, pages: 1, chunks: 4 });
    if (p.endsWith('/analyze')) { const r = opts.analyze?.() ?? report(); return typeof r === 'number' ? ok({ detail: 'Gemini unavailable' }, r) : ok(r); }
    if (p === '/query') { const r = opts.query?.() ?? query(); return typeof r === 'number' ? ok({ detail: 'Embedding service unavailable' }, r) : ok(r); }
    if (p === '/audit/verify') return ok(opts.verify ?? { valid: true, rows: 3, broken_at_id: null, reason: '', head_hash: 'abc' });
    if (p === '/audit') return ok([]);
    if (m === 'DELETE') return ok({ deleted: 'aaaaaaaaaaaa' });
    return ok({ detail: 'unmocked ' + p }, 404);
  });
}

export async function loadAndAnalyze(page: Page) {
  await page.goto('/workspace');
  await page.getByRole('button', { name: 'Use this sample' }).first().click();
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await page.getByRole('link', { name: 'View report' }).click();
}
