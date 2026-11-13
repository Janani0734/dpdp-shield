import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ServerStatusStore } from '../../core/server-status.store';
import { WorkspaceStore } from '../../core/workspace.store';

@Component({
  selector: 'app-dashboard-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <div class="page">
      <h1>Dashboard</h1>
      <p class="muted">Counts below come only from reports run in this browser session. Reports are not stored on the server.</p>

      <section class="card" aria-labelledby="mode-h">
        <h2 id="mode-h">Analysis mode</h2>
        @switch (status.state()) {
          @case ('loading') { <p role="status">Checking the API…</p> }
          @case ('error') { <p class="banner danger" role="alert">{{ status.error()?.message }}</p> }
          @default {
            @if (status.health()?.mode === 'gemini') {
              <p>A Gemini key is configured on the server. Whether a given call succeeds is reported per report and per answer.</p>
            } @else {
              <p>Offline mode: deterministic rule checks and template fix drafts only; no model is called.</p>
            }
            <p class="muted">Knowledge base: {{ status.health()?.kb_chunks }} chunks · embeddings: {{ status.health()?.embeddings }}</p>
            @for (w of status.health()?.warnings ?? []; track w) { <p class="banner warn">{{ w }}</p> }
          }
        }
      </section>

      @if (reports().length === 0) {
        <div class="empty">
          <p>No reports yet. Choose a policy and run an analysis to see counts here.</p>
          <a class="btn primary" routerLink="/workspace">Open Policy workspace</a>
        </div>
      } @else {
        <div class="grid-cards">
          <div class="card stat"><div class="muted">Reports this session</div><strong>{{ reports().length }}</strong></div>
          <div class="card stat"><div class="muted">Potential gaps (deterministic rules)</div><strong>{{ totals().rules }}</strong></div>
          <div class="card stat"><div class="muted">AI-suggested gaps (verify)</div><strong>{{ totals().llm }}</strong></div>
          <div class="card stat"><div class="muted">Reports with Gemini fallback</div><strong>{{ totals().skipped }}</strong></div>
        </div>
        <section class="card" aria-labelledby="rep-h">
          <h2 id="rep-h">Reports</h2>
          <table>
            <thead><tr><th scope="col">Policy</th><th scope="col">Mode</th><th scope="col">Rule gaps</th><th scope="col">AI-suggested</th><th scope="col">High / Med / Low</th></tr></thead>
            <tbody>
              @for (r of reports(); track r.policy_id) {
                <tr>
                  <th scope="row"><a routerLink="/report" (click)="workspace.select(r.policy_id)">{{ r.policy_name }}</a></th>
                  <td>{{ r.mode }}</td>
                  <td>{{ r.summary.failed }}</td>
                  <td>{{ r.summary.llm_extra_gaps }}</td>
                  <td>{{ r.summary.by_severity.high }} / {{ r.summary.by_severity.medium }} / {{ r.summary.by_severity.low }}</td>
                </tr>
              }
            </tbody>
          </table>
        </section>
      }
      <p class="muted small">These are potential gaps from automated checks, not legal findings.</p>
    </div>
  `,
  styles: `table { width: 100%; border-collapse: collapse; } th, td { text-align: left; padding: .5rem; border-bottom: 1px solid var(--app-border); }`,
})
export class DashboardPage {
  protected readonly status = inject(ServerStatusStore);
  protected readonly workspace = inject(WorkspaceStore);
  protected readonly reports = this.workspace.analyzedReports;
  protected readonly totals = computed(() => {
    const rs = this.reports();
    return {
      rules: rs.reduce((n, r) => n + r.summary.failed, 0),
      llm: rs.reduce((n, r) => n + r.summary.llm_extra_gaps, 0),
      skipped: rs.filter((r) => r.warnings.some((w) => w.startsWith('Gemini review skipped'))).length,
    };
  });
}
