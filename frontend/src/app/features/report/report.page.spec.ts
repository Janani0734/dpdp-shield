import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';
import { Report, ReportRow } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { ReportPage } from './report.page';

const row = (o: Partial<ReportRow>): ReportRow => ({ section: 'S', status: 'fail', severity: 'high', dpdp_ref: 'Sec 5', violation_type: 'v', requirement: 'req', evidence: { snippet: '', page: null }, fix_suggestion: 'draft', fix_source: 'template', penalty_exposure: '', review_note: '', detected_by: 'rules', ...o });

describe('ReportPage', () => {
  let el: HTMLElement;
  let fixture: ReturnType<typeof TestBed.createComponent<ReportPage>>;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const store = TestBed.inject(WorkspaceStore);
    const rep: Report = {
      policy_id: 'p', policy_name: 'Pol', generated_at: 't', mode: 'gemini', disclaimer: 'D', warnings: ['Gemini review skipped: quota'],
      summary: { total_checks: 3, passed: 1, failed: 2, llm_extra_gaps: 1, by_severity: { high: 2, medium: 1, low: 0 }, highest_penalty_ceiling_crore: 250, note: '' },
      rows: [row({ section: 'A', severity: 'high' }), row({ section: 'B', status: 'pass', severity: 'low', evidence: { snippet: 'we notify', page: 2 } }), row({ section: 'C', severity: 'medium', detected_by: 'llm' })],
    };
    store.policies.set([{ id: 'p', name: 'Pol', pages: 1, chunks: 1, origin: 'sample', createdAt: '' }]);
    store.reports.set({ p: rep });
    store.select('p');
    fixture = TestBed.createComponent(ReportPage);
    fixture.detectChanges();
    el = fixture.nativeElement;
  });

  const titles = () => Array.from(el.querySelectorAll('article h2')).map((h) => h.textContent?.trim());

  it('uses "potential gap" wording, never "violation" or "compliant" claims', () => {
    expect(el.textContent).toContain('Potential gap');
    expect(el.textContent).toContain('not a legal');
    const withoutDisclaimer = (el.textContent ?? '').replace(/does not mean the policy is compliant/, '');
    expect(withoutDisclaimer).not.toMatch(/compliant|violation/i);
  });

  it('shows the Gemini-skipped fallback state from backend warnings', () => {
    expect(el.textContent).toContain('review was skipped');
  });

  it('filters by status, severity and finding source', () => {
    expect(titles()).toEqual(['A', 'B', 'C']);
    const [status, severity, source] = Array.from(el.querySelectorAll('select'));
    status!.value = 'fail'; status!.dispatchEvent(new Event('change')); fixture.detectChanges();
    expect(titles()).toEqual(['A', 'C']);
    source!.value = 'llm'; source!.dispatchEvent(new Event('change')); fixture.detectChanges();
    expect(titles()).toEqual(['C']);
    source!.value = 'all'; source!.dispatchEvent(new Event('change'));
    severity!.value = 'high'; severity!.dispatchEvent(new Event('change')); fixture.detectChanges();
    expect(titles()).toEqual(['A']);
  });

  it('labels AI-suggested rows and shows evidence page', () => {
    expect(el.textContent).toContain('AI-suggested — verify');
    expect(el.textContent).toContain('Policy page 2');
  });
});
