import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ReportRow, Severity } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';

type StatusFilter = 'all' | 'fail' | 'pass';
type SourceFilter = 'all' | 'rules' | 'llm';
type SevFilter = 'all' | Severity;

@Component({
  selector: 'app-report-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <div class="page">
      <h1>Gap report</h1>
      @if (!report(); as _) {
        <div class="empty">
          <p>No report for the selected policy yet.</p>
          <a class="btn primary" routerLink="/workspace">Go to Policy workspace</a>
        </div>
      } @else {
        <p class="muted">{{ report()!.policy_name }} · generated {{ generated() }}</p>

        <div class="banner info"><span>
          Results are <strong>potential gaps</strong> found by keyword rules and an AI reviewer, shown for review. They are not a legal
          finding, and a check that “passes” does not mean the policy is compliant. Consult a qualified professional.
        </span></div>

        @if (report()!.mode === 'offline') {
          <div class="banner warn" role="status">Offline mode: rule-based checks only; fix drafts come from fixed templates.</div>
        } @else if (geminiSkipped()) {
          <div class="banner warn" role="status">Gemini is configured but its review was skipped; showing rule-based results with template fixes.</div>
        }
        @for (w of report()!.warnings; track w) { <div class="banner warn" role="status">{{ w }}</div> }

        <div class="grid-cards">
          <div class="card stat"><div class="muted">Rule checks</div><strong>{{ report()!.summary.total_checks }}</strong></div>
          <div class="card stat"><div class="muted">Potential gaps (rules)</div><strong>{{ report()!.summary.failed }}</strong></div>
          <div class="card stat"><div class="muted">Extra gaps suggested by AI</div><strong>{{ report()!.summary.llm_extra_gaps }}</strong></div>
          <div class="card stat"><div class="muted">Rule checks with keywords found</div><strong>{{ report()!.summary.passed }}</strong></div>
        </div>

        <fieldset class="filters">
          <legend>Filters</legend>
          <label>Status
            <select [value]="status()" (change)="status.set($any($event.target).value)">
              <option value="all">All</option><option value="fail">Potential gap</option><option value="pass">Keywords found</option>
            </select></label>
          <label>Severity
            <select [value]="severity()" (change)="severity.set($any($event.target).value)">
              <option value="all">All</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
            </select></label>
          <label>Finding source
            <select [value]="source()" (change)="source.set($any($event.target).value)">
              <option value="all">All</option><option value="rules">Deterministic rules</option><option value="llm">AI suggestion</option>
            </select></label>
        </fieldset>
        <p class="muted" role="status">Showing {{ filtered().length }} of {{ report()!.rows.length }}</p>

        @if (filtered().length === 0) {
          <div class="empty"><p>No rows match these filters.</p></div>
        }
        @for (r of filtered(); track $index) {
          <article class="card row-card">
            <header>
              <h2>{{ r.section }}</h2>
              <span class="pill" [class.warn]="r.status === 'fail'" [class.neutral]="r.status === 'pass'">{{ r.status === 'fail' ? 'Potential gap' : 'Keywords found' }}</span>
              <span [class]="'sev ' + r.severity" [class.dim]="r.status === 'pass'">{{ r.severity }} {{ r.status === 'pass' ? 'priority check' : 'severity' }}</span>
              <span class="pill neutral">{{ r.detected_by === 'rules' ? 'Deterministic rule' : 'AI-suggested — verify' }}</span>
            </header>
            <p><strong>Reference:</strong> {{ r.dpdp_ref }}</p>
            <p>{{ r.requirement }}</p>
            @if (r.evidence.snippet) {
              <blockquote>{{ r.evidence.snippet }}<footer class="muted small">{{ r.evidence.page ? 'Policy page ' + r.evidence.page : 'Page not available' }}</footer></blockquote>
            } @else if (r.status === 'fail' && r.detected_by === 'rules') {
              <p class="muted">No matching text was found in the policy.</p>
            } @else if (r.status === 'fail') {
              <p class="muted">The AI reviewer did not quote policy text for this suggestion. Verify it against the policy.</p>
              <p class="muted small">AI suggestions can differ from one run to the next; only the rule-based results are repeatable.</p>
            }
            @if (r.review_note) { <div class="banner warn"><span><strong>AI review note (advisory):</strong> {{ r.review_note }}</span></div> }
            @if (r.status === 'fail' && r.fix_suggestion) {
              <details>
                <summary>Suggested draft ({{ r.fix_source === 'gemini' ? 'written by Gemini' : r.fix_source === 'template' ? 'fixed template' : 'source unknown' }})</summary>
                <p class="draft">{{ r.fix_suggestion }}</p>
                <button type="button" class="btn" (click)="copy(r.fix_suggestion)">Copy draft</button>
                <p class="muted small">A starting point only — review before use.</p>
              </details>
            }
            @if (r.status === 'fail' && r.penalty_exposure) { <p class="muted small">Penalty ceiling in the Act’s schedule: {{ r.penalty_exposure }}</p> }
          </article>
        }
        <p class="muted small">{{ report()!.disclaimer }}</p>
      }
    </div>
  `,
  styles: `
    .filters { display: flex; flex-wrap: wrap; gap: 1rem; border: 1px solid var(--app-border); border-radius: 10px; padding: .75rem 1rem; margin: 1rem 0; }
    .filters label { display: grid; gap: .25rem; }
    .row-card { display: grid; gap: .5rem; margin-bottom: 1rem; }
    .row-card header { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
    .row-card h2 { margin: 0 .5rem 0 0; font-size: 1.1rem; }
    blockquote { margin: 0; padding: .5rem .9rem; border-left: 3px solid var(--app-navy-700); background: var(--app-bg); }
    .draft { white-space: pre-wrap; }
    .sev.dim { color: var(--app-slate-600) !important; font-weight: 500; }
  `,
})
export class ReportPage {
  private readonly store = inject(WorkspaceStore);
  protected readonly report = this.store.selectedReport;
  /** Local date/time; falls back to the raw text if the backend value is not a valid date. */
  protected readonly generated = computed(() => {
    const raw = this.report()?.generated_at ?? '';
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? raw : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  });
  protected readonly status = signal<StatusFilter>('all');
  protected readonly severity = signal<SevFilter>('all');
  protected readonly source = signal<SourceFilter>('all');

  protected readonly geminiSkipped = computed(() => this.report()?.warnings.some((w) => w.startsWith('Gemini review skipped')) ?? false);

  protected readonly filtered = computed<ReportRow[]>(() => {
    const rows = this.report()?.rows ?? [];
    return rows.filter(
      (r) =>
        (this.status() === 'all' || r.status === this.status()) &&
        (this.severity() === 'all' || r.severity === this.severity()) &&
        (this.source() === 'all' || r.detected_by === this.source()),
    );
  });

  protected copy(text: string): void {
    void navigator.clipboard?.writeText(text);
  }
}
