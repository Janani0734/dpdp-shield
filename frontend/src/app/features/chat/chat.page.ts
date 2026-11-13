import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ChatStore } from '../../core/chat.store';
import { Citation, QueryResult } from '../../core/models';
import { ServerStatusStore } from '../../core/server-status.store';
import { WorkspaceStore } from '../../core/workspace.store';

@Component({
  selector: 'app-chat-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <div class="page">
      <h1>Ask questions</h1>
      @if (!workspace.selected(); as _) {
        <div class="empty">
          <p>Select or add a policy first. Questions are answered about the selected policy and the DPDP Act and Rules.</p>
          <a class="btn primary" routerLink="/workspace">Go to Policy workspace</a>
        </div>
      } @else {
        <p class="muted">Policy: <strong>{{ workspace.selected()!.name }}</strong></p>

        <form (submit)="$event.preventDefault(); submit()">
          <label for="q">Your question</label>
          <textarea id="q" rows="3" [value]="question()" [attr.maxlength]="max()" (input)="onInput($event)" [disabled]="!!chat.pendingQuestion()" aria-describedby="q-help"></textarea>
          <div class="row">
            <span id="q-help" class="muted small">{{ question().trim().length }} / {{ max() }}. Each question is recorded in the audit log.</span>
            @if (chat.pendingQuestion()) {
              <button type="button" class="btn" (click)="chat.cancel()">Stop waiting</button>
            } @else {
              <button type="submit" class="btn primary" [disabled]="!question().trim()">Ask</button>
            }
          </div>
        </form>

        @if (chat.pendingQuestion(); as q) {
          <p role="status" class="card">Working on: “{{ q }}” — this can take several seconds.</p>
        }
        @if (chat.error(); as e) { <div class="banner danger" role="alert">{{ e.message }}</div> }

        @if (turns().length === 0 && !chat.pendingQuestion()) {
          <div class="empty"><p>No questions yet. For example: “Does this policy explain how to withdraw consent?”</p></div>
        }

        @for (t of turns(); track t.id) {
          <article class="card turn" [attr.aria-label]="'Answer to ' + t.question">
            <h2>{{ t.question }}</h2>
            @if (t.result.mode === 'gemini-fallback') {
              <div class="banner warn">Gemini was configured but the call failed or returned nothing; this answer is rule-based.</div>
            } @else if (t.result.mode === 'offline') {
              <div class="banner info">Offline mode: answer built from rules and retrieved sources, without a language model.</div>
            }
            @for (w of t.result.warnings; track w) { <div class="banner warn">{{ w }}</div> }
            <p class="answer">{{ t.result.answer }}</p>

            @if (t.result.violations.length) {
              <h3>Potential gaps noted</h3>
              <ul>
                @for (v of t.result.violations; track $index) {
                  <li><span [class]="'sev ' + v.severity">{{ v.severity }}</span> — {{ vtype(v.type) }}
                    <span class="muted small">({{ v.source === 'rules' ? 'deterministic rule' : v.source === 'llm' ? 'AI suggestion — verify' : 'rule + AI' }})</span>
                    @if (v.fix) { <div class="muted">{{ v.fix }}</div> }</li>
                }
              </ul>
            }

            <h3>Citations</h3>
            @if (t.result.citations.length === 0) {
              <p class="muted">No sources were returned for this answer.</p>
            } @else {
              <ul class="cites">
                @for (c of t.result.citations; track $index) {
                  <li class="cite">
                    <strong>{{ label(c.section, c) }}</strong>@if (hasText(c.title)) { · {{ c.title }} }
                    <div class="muted small">{{ c.source }} · {{ c.page ? 'PDF page ' + c.page : 'page not available' }} · {{ scope(c) }}</div>
                    @if (unofficial(c)) { <span class="pill warn">Unofficial summary — not the Gazette text</span> }
                  </li>
                }
              </ul>
              <p class="muted small">Citations show where the answer’s sources come from. The server does not return the retrieved passages, so none are shown.</p>
            }
            <p class="muted small">Heuristic confidence {{ (t.result.confidence * 100).toFixed(0) }}% (not a probability) · {{ seconds(t.result.latency_ms) }} · mode {{ t.result.mode }}</p>
          </article>
        }
        <p class="muted small">Informational only; not legal advice.</p>
      }
    </div>
  `,
  styles: `
    textarea { width: 100%; box-sizing: border-box; }
    form { display: grid; gap: .5rem; margin-bottom: 1rem; }
    .turn { display: grid; gap: .5rem; margin-bottom: 1rem; }
    .turn h2 { font-size: 1.05rem; margin: 0; }
    .answer { white-space: pre-wrap; }
    .cites { list-style: none; padding: 0; display: grid; gap: .5rem; }
    .cite { padding: .6rem .8rem; border: 1px solid var(--app-border); border-radius: 8px; background: var(--app-bg); }
  `,
})
export class ChatPage {
  protected readonly workspace = inject(WorkspaceStore);
  protected readonly chat = inject(ChatStore);
  private readonly status = inject(ServerStatusStore);

  protected readonly question = signal('');
  protected readonly max = computed(() => this.status.config()?.max_question_chars ?? 1000);
  protected readonly turns = computed(() => this.chat.turns().filter((t) => t.policyId === this.workspace.selectedId()));

  protected onInput(ev: Event): void {
    this.question.set((ev.target as HTMLTextAreaElement).value);
  }

  protected submit(): void {
    const id = this.workspace.selectedId();
    const q = this.question().trim();
    if (!id || !q || q.length > this.max()) return;
    this.chat.ask(id, q);
    this.question.set('');
  }

  private static readonly WORD = /[\p{L}\p{N}]/u;
  protected hasText(s: string | null | undefined): boolean { return !!s && ChatPage.WORD.test(s); }
  /** Section label; a policy chunk without a usable heading (e.g. ".") is shown as a generic excerpt label. */
  protected label(section: string, c: Citation): string {
    if (this.hasText(section)) return section;
    return c.scope === 'policy' ? 'Policy excerpt' : 'Source';
  }
  /** `missing_breach_notification` → `Missing breach notification` (display only). */
  protected vtype(t: string): string {
    const x = t.replace(/_/g, ' ').trim();
    return x ? x.charAt(0).toUpperCase() + x.slice(1) : 'Potential gap';
  }
  protected seconds(ms: number): string { return ms >= 1000 ? (ms / 1000).toFixed(1) + ' s' : ms + ' ms'; }

  protected scope(c: Citation): string {
    return c.scope === 'policy' ? 'your policy' : 'DPDP law';
  }
  protected unofficial(c: Citation): boolean {
    return c.origin === 'working-summary' || c.origin === 'project-template';
  }
}
export type { QueryResult };
