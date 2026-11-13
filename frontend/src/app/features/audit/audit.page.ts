import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiError, toApiError } from '../../core/api-error';
import { ApiService } from '../../core/api.service';
import { AuditRow, AuditVerifyResult } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';

@Component({
  selector: 'app-audit-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <div class="page">
      <h1>Audit</h1>
      <p class="muted">Every ingest, analysis and question is written to a hash-chained log on the server.</p>

      <section class="card" aria-labelledby="v-h">
        <h2 id="v-h">Verify the chain</h2>
        <p>Recomputes every link in the server’s log. The check covers the whole log but returns only counts and hashes — no one’s records.</p>
        <button type="button" class="btn primary" [disabled]="verifying()" (click)="verify()">{{ verifying() ? 'Verifying…' : 'Verify audit log' }}</button>
        @if (verifyError(); as e) { <div class="banner danger" role="alert">{{ e.message }}</div> }
        @if (result(); as r) {
          <div class="banner" [class.info]="r.valid" [class.danger]="!r.valid" role="status">
            @if (r.valid) { <span>Chain intact: {{ r.rows }} entries; no edited or removed entries detected.</span> }
            @else { <span>Chain broken at entry {{ r.broken_at_id }}: {{ r.reason }}</span> }
          </div>
          <p class="muted small">Head hash: <code>{{ r.head_hash }}</code></p>
        }
        <h3>What this does not prove</h3>
        <ul class="small">
          <li>It detects edits and deletions of individual entries. Someone with write access to the whole database file could rebuild the chain; to guard against that, record the head hash somewhere you trust.</li>
          <li>It shows the log was not altered, not that any analysis or answer was correct.</li>
          <li>Entries include the question text you submit and cannot be deleted individually without breaking the chain.</li>
        </ul>
      </section>

      <section class="card" aria-labelledby="e-h">
        <h2 id="e-h">Entries for the selected policy</h2>
        @if (!workspace.selected()) {
          <div class="empty"><p>Select a policy to list its entries. Entries from other policies are never shown here.</p><a class="btn" routerLink="/workspace">Go to Policy workspace</a></div>
        } @else {
          <button type="button" class="btn" [disabled]="loading()" (click)="load()">{{ loading() ? 'Loading…' : 'Load entries for ' + workspace.selected()!.name }}</button>
          @if (listError(); as e) { <div class="banner danger" role="alert">{{ e.message }}</div> }
          @if (rows(); as list) {
            @if (list.length === 0) { <p class="muted">No entries yet.</p> } @else {
              <table>
                <thead><tr><th scope="col">#</th><th scope="col">Time (UTC)</th><th scope="col">Event</th><th scope="col">Question / summary</th><th scope="col">Hash</th></tr></thead>
                <tbody>
                  @for (a of list; track a.id) {
                    <tr><td>{{ a.id }}</td><td>{{ a.timestamp }}</td><td>{{ a.event }}</td><td>{{ a.user_query || a.answer_summary }}</td><td><code>{{ a.row_hash.slice(0, 12) }}…</code></td></tr>
                  }
                </tbody>
              </table>
            }
          }
        }
      </section>
    </div>
  `,
  styles: `table { width: 100%; border-collapse: collapse; } th, td { text-align: left; padding: .4rem; border-bottom: 1px solid var(--app-border); vertical-align: top; overflow-wrap: anywhere; } code { word-break: break-all; }`,
})
export class AuditPage {
  private readonly api = inject(ApiService);
  protected readonly workspace = inject(WorkspaceStore);

  protected readonly result = signal<AuditVerifyResult | null>(null);
  protected readonly verifying = signal(false);
  protected readonly verifyError = signal<ApiError | null>(null);
  protected readonly rows = signal<AuditRow[] | null>(null);
  protected readonly loading = signal(false);
  protected readonly listError = signal<ApiError | null>(null);

  protected verify(): void {
    this.verifying.set(true);
    this.verifyError.set(null);
    this.api.verifyAudit().subscribe({
      next: (r) => { this.result.set(r); this.verifying.set(false); },
      error: (e: unknown) => { this.verifyError.set(toApiError(e)); this.verifying.set(false); },
    });
  }

  protected load(): void {
    const id = this.workspace.selectedId();
    if (!id) return;
    this.loading.set(true);
    this.listError.set(null);
    this.api.audit(id).subscribe({
      next: (r) => { this.rows.set(r); this.loading.set(false); },
      error: (e: unknown) => { this.listError.set(toApiError(e)); this.loading.set(false); },
    });
  }
}
