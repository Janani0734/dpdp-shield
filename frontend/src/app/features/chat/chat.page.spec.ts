import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';
import { AppConfigService } from '../../core/app-config.service';
import { QueryResult } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { ChatPage } from './chat.page';

const result = (o: Partial<QueryResult> = {}): QueryResult => ({
  answer: 'Section 8 requires safeguards.', citations: [
    { source: 'DPDP Act 2023', section: 'Section 8', title: 'General obligations', page: 7, origin: 'official-pdf', scope: 'dpdp' },
    { source: 'CERT-In summary', section: 'Breach', title: 'Summary', page: null, origin: 'working-summary', scope: 'dpdp' },
  ], violations: [{ type: 'no_breach_notice', severity: 'high', fix: 'Add a notice clause', source: 'llm' }], confidence: 0.6, mode: 'gemini', latency_ms: 1200,
  timings: { embed_ms: 1, retrieve_ms: 1, llm_ms: 1 }, warnings: [], policy_id: 'p', audit: { id: 1, row_hash: 'h' }, ...o,
});

describe('ChatPage', () => {
  let ctl: HttpTestingController;
  let f: ReturnType<typeof TestBed.createComponent<ChatPage>>;
  const el = () => f.nativeElement as HTMLElement;
  const type = (t: string) => { const ta = el().querySelector('textarea')!; ta.value = t; ta.dispatchEvent(new Event('input')); f.detectChanges(); };
  const submit = () => { el().querySelector('form')!.dispatchEvent(new Event('submit')); f.detectChanges(); };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    TestBed.inject(AppConfigService).apiBaseUrl.set('http://api.test');
    ctl = TestBed.inject(HttpTestingController);
  });
  function withPolicy() {
    const ws = TestBed.inject(WorkspaceStore);
    ws.policies.set([{ id: 'p', name: 'Pol', pages: 1, chunks: 1, origin: 'sample', createdAt: '' }]);
    ws.select('p');
    f = TestBed.createComponent(ChatPage); f.detectChanges();
  }

  it('shows an empty state asking for a policy when none is selected', () => {
    f = TestBed.createComponent(ChatPage); f.detectChanges();
    expect(el().textContent).toContain('Select or add a policy first');
    expect(el().querySelector('textarea')).toBeNull();
  });

  it('sends the question for the selected policy and renders citations without invented evidence', () => {
    withPolicy();
    type('What about breaches?'); submit();
    expect(el().textContent).toContain('Working on');
    const req = ctl.expectOne('http://api.test/query');
    expect(req.request.body).toEqual({ policy_id: 'p', question: 'What about breaches?' });
    req.flush(result()); f.detectChanges();
    const t = el().textContent ?? '';
    expect(t).toContain('Section 8'); expect(t).toContain('PDF page 7'); expect(t).toContain('page not available');
    expect(t).toContain('Unofficial summary'); expect(t).toContain('AI suggestion — verify');
    expect(t).toContain('does not return the retrieved passages');
  });

  it('labels a Gemini fallback and shows backend warnings', () => {
    withPolicy(); type('q'); submit();
    ctl.expectOne('http://api.test/query').flush(result({ mode: 'gemini-fallback', warnings: ['Gemini call failed: 503'] })); f.detectChanges();
    expect(el().textContent).toContain('answer is rule-based');
    expect(el().textContent).toContain('Gemini call failed: 503');
  });

  it('shows an error and allows asking again; does not auto-retry', () => {
    withPolicy(); type('q'); submit();
    ctl.expectOne('http://api.test/query').flush({ detail: 'Embedding service unavailable' }, { status: 503, statusText: 'x' }); f.detectChanges();
    expect(el().querySelector('[role=alert]')?.textContent).toContain('Embedding service unavailable');
    ctl.verify();
  });

  it('cancel stops waiting and issues no second request', () => {
    withPolicy(); type('q'); submit();
    (Array.from(el().querySelectorAll('button')).find((b) => b.textContent?.includes('Stop waiting')) as HTMLButtonElement).click(); f.detectChanges();
    expect(ctl.expectOne('http://api.test/query').cancelled).toBe(true);
    expect(el().textContent).not.toContain('Working on');
  });

  it('never renders a punctuation-only citation heading and prettifies violation types', () => {
    withPolicy();
    type('Does it cover breaches?'); submit();
    ctl.expectOne('http://api.test/query').flush(result({
      citations: [{ source: 'Uploaded policy', section: '.', title: '', page: 1, origin: 'user-policy', scope: 'policy' }],
      violations: [{ type: 'missing_breach_notification', severity: 'high', fix: '', source: 'rules' }],
      latency_ms: 16820,
    }));
    f.detectChanges();
    const t = el().textContent ?? '';
    expect(el().querySelector('.cite strong')?.textContent?.trim()).toBe('Policy excerpt');
    expect(t).toContain('Missing breach notification');
    expect(t).not.toContain('missing_breach_notification');
    expect(t).toContain('16.8 s');
  });
});
