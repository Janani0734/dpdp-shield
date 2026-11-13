import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiError, toApiError } from '../../core/api-error';
import { ApiService } from '../../core/api.service';
import { SampleInfo } from '../../core/models';
import { ServerStatusStore } from '../../core/server-status.store';
import { WorkspaceStore } from '../../core/workspace.store';
import { AppIcon } from '../../shared/icon';

@Component({
  selector: 'app-workspace-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, AppIcon],
  template: `
    <div class="page">
      <h1>Policy workspace</h1>
      <p class="muted">Choose a policy to check. Nothing is analysed until you press “Run analysis”.</p>

      @if (store.error(); as e) {
        <div class="banner danger" role="alert">{{ e.message }} <button type="button" class="btn link" (click)="store.clearError()">Dismiss</button></div>
      }

      <section class="card" aria-labelledby="samples-h">
        <h2 id="samples-h">Bundled samples</h2>
        @if (samplesError(); as se) {
          <div class="banner danger" role="alert">{{ se.message }}</div>
        } @else if (samples() === null) {
          <p class="muted" role="status">Loading samples…</p>
        } @else {
          <div class="grid-cards">
            @for (s of samples(); track s.id) {
              <div class="card inner">
                <h3>{{ s.title }}</h3>
                <p class="muted">{{ s.description }}</p>
                <button type="button" class="btn" [disabled]="!s.available || store.adding()" (click)="store.addSample(s.id)">
                  {{ store.adding() ? 'Loading…' : s.available ? 'Use this sample' : 'Unavailable' }}
                </button>
              </div>
            }
          </div>
        }
      </section>

      @if (status.uploadsEnabled()) {
        <section class="card" aria-labelledby="up-h">
          <h2 id="up-h">Your own policy</h2>
          <div class="banner info"><span>
            <strong>Privacy notice.</strong> Your policy text is sent to this server, indexed locally, and — if a Gemini key is configured —
            excerpts are sent to Google's Gemini API for review. Questions you ask are kept in a tamper-evident audit log that cannot be
            deleted individually. Do not upload documents containing personal data.
          </span></div>
          <label class="check"><input type="checkbox" [checked]="ack()" (change)="ack.set(!ack())" /> I understand and want to continue</label>

          <div class="stack">
            <label for="pdf">PDF (max {{ limits()?.max_pdf_mb }} MB, {{ limits()?.max_pdf_pages }} pages)</label>
            <input id="pdf" type="file" accept="application/pdf,.pdf" [disabled]="!ack() || store.adding()" (change)="onFile($event)" />
            @if (fileError()) { <p class="field-error" role="alert">{{ fileError() }}</p> }
          </div>

          <div class="stack">
            <label for="txt">Or paste policy text ({{ limits()?.min_text_chars }}–{{ limits()?.max_text_chars }} characters)</label>
            <textarea id="txt" rows="6" [value]="text()" [disabled]="!ack() || store.adding()" (input)="onText($event)"></textarea>
            <div class="row">
              <span class="muted">{{ text().trim().length }} characters</span>
              <button type="button" class="btn" [disabled]="!ack() || store.adding() || !!textError() || !text().trim()" (click)="submitText()">Add pasted text</button>
            </div>
            @if (textError() && text().trim()) { <p class="field-error" role="alert">{{ textError() }}</p> }
          </div>
        </section>
      } @else if (status.state() === 'ready') {
        <div class="banner info">Uploads are disabled on this server. Use a bundled sample.</div>
      }

      <section class="card" aria-labelledby="list-h">
        <h2 id="list-h">Policies in this session</h2>
        @if (store.policies().length === 0) {
          <div class="empty"><p>No policy yet. Pick a sample above to begin.</p></div>
        } @else {
          <ul class="plain">
            @for (p of store.policies(); track p.id) {
              <li class="policy" [class.active]="p.id === store.selectedId()">
                <button type="button" class="btn link" [attr.aria-pressed]="p.id === store.selectedId()" (click)="store.select(p.id)">{{ p.name }}</button>
                <span class="muted">{{ p.pages }} page(s) · {{ p.chunks }} chunks · {{ p.origin }}</span>
                <span class="row">
                  @if (store.analyzingId() === p.id) {
                    <span role="status">Analysing…</span>
                    <button type="button" class="btn" (click)="store.cancelAnalyze()">Stop waiting</button>
                  } @else {
                    <button type="button" class="btn primary" [disabled]="!!store.analyzingId()" (click)="store.analyze(p.id)">
                      {{ store.reports()[p.id] ? 'Re-run analysis' : 'Run analysis' }}
                    </button>
                  }
                  @if (store.reports()[p.id]) { <a class="btn" routerLink="/report" (click)="store.select(p.id)">View report</a> }
                  @if (confirmId() === p.id) {
                    <button type="button" class="btn danger" [disabled]="store.deletingId() === p.id" (click)="confirmDelete(p.id)">Confirm delete</button>
                    <button type="button" class="btn" (click)="confirmId.set(null)">Cancel</button>
                  } @else {
                    <button type="button" class="btn" (click)="confirmId.set(p.id)"><app-icon name="trash" /> Delete</button>
                  }
                </span>
              </li>
            }
          </ul>
          <p class="muted small">Re-running analysis repeats the review (and any Gemini call). Deleting removes the indexed policy and this session's report; audit entries remain.</p>
        }
      </section>
    </div>
  `,
  styles: `
    .stack { display: grid; gap: .4rem; margin: 1rem 0; }
    textarea { width: 100%; font: inherit; padding: .6rem; border: 1px solid #6b7a93; border-radius: 8px; }
    .check { display: flex; gap: .5rem; align-items: center; margin: .5rem 0; }
    .plain { list-style: none; padding: 0; margin: 0; display: grid; gap: .75rem; }
    .policy { display: grid; gap: .4rem; padding: .75rem; border: 1px solid var(--app-border); border-radius: 8px; }
    .policy.active { border-color: var(--app-navy-700); }
    .inner { box-shadow: none; }
  `,
})
export class WorkspacePage implements OnInit {
  protected readonly store = inject(WorkspaceStore);
  protected readonly status = inject(ServerStatusStore);
  private readonly api = inject(ApiService);

  protected readonly samples = signal<SampleInfo[] | null>(null);
  protected readonly samplesError = signal<ApiError | null>(null);
  protected readonly ack = signal(false);
  protected readonly text = signal('');
  protected readonly fileError = signal('');
  protected readonly confirmId = signal<string | null>(null);
  protected readonly limits = this.status.config;

  protected readonly textError = computed(() => {
    const c = this.limits();
    const n = this.text().trim().length;
    if (!c || n === 0) return '';
    if (n < c.min_text_chars) return `Enter at least ${c.min_text_chars} characters.`;
    if (n > c.max_text_chars) return `Text is too long (max ${c.max_text_chars} characters).`;
    return '';
  });

  ngOnInit(): void {
    this.api.samples().subscribe({
      next: (s) => this.samples.set(s),
      error: (e: unknown) => this.samplesError.set(toApiError(e)),
    });
  }

  protected onText(ev: Event): void {
    this.text.set((ev.target as HTMLTextAreaElement).value);
  }

  protected onFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    this.fileError.set('');
    if (!file) return;
    const c = this.limits();
    if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') this.fileError.set('Please choose a PDF file.');
    else if (c && file.size > c.max_pdf_mb * 1024 * 1024) this.fileError.set(`File is larger than ${c.max_pdf_mb} MB.`);
    else this.store.addPdf(file);
    input.value = '';
  }

  protected submitText(): void {
    if (this.textError()) return;
    this.store.addText(this.text().trim());
    this.text.set('');
  }

  protected confirmDelete(id: string): void {
    this.confirmId.set(null);
    this.store.remove(id);
  }
}
