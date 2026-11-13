/**
 * Typed mirrors of the FastAPI responses. Derived from dpdp_shield/api.py, report.py, pipeline.py and audit.py
 * and checked against real responses (see docs/API_CONTRACT.md). Do not add fields the backend does not send.
 */
export type Severity = 'high' | 'medium' | 'low';
export type RowStatus = 'pass' | 'fail';
/** Backend `mode` on a report: `gemini` simply means a key is configured. Check `warnings` for a skipped review. */
export type ReportMode = 'gemini' | 'offline';
export type QueryMode = 'gemini' | 'gemini-fallback' | 'offline';

export interface HealthResponse {
  status: string;
  mode: ReportMode;
  embeddings: string;
  kb_chunks: number;
  warnings: string[];
}

export interface ServerConfig {
  demo_mode: boolean;
  uploads_enabled: boolean;
  max_pdf_pages: number;
  max_pdf_mb: number;
  min_text_chars: number;
  max_text_chars: number;
  max_question_chars: number;
  rate_limit_per_min: number;
}

export interface SampleInfo {
  id: string;
  title: string;
  description: string;
  available: boolean;
}

export interface PolicyUploadResponse {
  policy_id: string;
  name: string;
  pages: number;
  chunks: number;
}

export interface ReportRow {
  section: string;
  status: RowStatus;
  severity: Severity;
  dpdp_ref: string;
  violation_type: string;
  requirement: string;
  evidence: { snippet: string; page: number | null };
  fix_suggestion: string;
  fix_source: 'gemini' | 'template' | '';
  penalty_exposure: string;
  review_note: string;
  detected_by: 'rules' | 'llm';
}

export interface ReportSummary {
  total_checks: number;
  passed: number;
  failed: number;
  llm_extra_gaps: number;
  by_severity: Record<Severity, number>;
  highest_penalty_ceiling_crore: number;
  note: string;
}

export interface Report {
  policy_id: string;
  policy_name: string;
  generated_at: string;
  mode: ReportMode;
  summary: ReportSummary;
  rows: ReportRow[];
  warnings: string[];
  disclaimer: string;
}

export type CitationOrigin = 'official-pdf' | 'working-summary' | 'project-template' | 'user-policy' | '';

export interface Citation {
  source: string;
  section: string;
  title: string;
  page: number | null;
  origin: CitationOrigin;
  scope: 'dpdp' | 'policy';
}

export interface QueryViolation {
  type: string;
  severity: Severity;
  fix: string;
  source: 'rules' | 'rules+llm' | 'llm';
}

export interface QueryResult {
  answer: string;
  citations: Citation[];
  violations: QueryViolation[];
  confidence: number;
  mode: QueryMode;
  latency_ms: number;
  timings: { embed_ms: number; retrieve_ms: number; llm_ms: number };
  warnings: string[];
  policy_id: string;
  audit: { id: number; row_hash: string };
}

export interface AuditRow {
  id: number;
  timestamp: string;
  event: 'ingest' | 'analyze' | 'query';
  policy_id: string;
  user_query: string;
  answer_summary: string;
  violation_count: number;
  prev_hash: string;
  row_hash: string;
}

export interface AuditVerifyResult {
  valid: boolean;
  rows: number;
  broken_at_id: number | null;
  reason: string;
  head_hash: string;
}

/** A policy known to this browser session (the backend has no list endpoint by design). */
export interface SessionPolicy {
  id: string;
  name: string;
  pages: number;
  chunks: number;
  origin: 'sample' | 'pdf' | 'text';
  /** Set for bundled samples so re-choosing one reuses it instead of creating a duplicate. */
  sampleId?: string;
  createdAt: string;
}
