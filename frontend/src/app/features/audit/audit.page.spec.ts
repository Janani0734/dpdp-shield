import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';
import { AppConfigService } from '../../core/app-config.service';
import { WorkspaceStore } from '../../core/workspace.store';
import { AuditPage } from './audit.page';

describe('AuditPage', () => {
  let ctl: HttpTestingController;
  let f: ReturnType<typeof TestBed.createComponent<AuditPage>>;
  const el = () => f.nativeElement as HTMLElement;
  const click = (label: string) => (Array.from(el().querySelectorAll('button')).find((b) => b.textContent?.includes(label)) as HTMLButtonElement).click();

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    TestBed.inject(AppConfigService).apiBaseUrl.set('http://api.test');
    ctl = TestBed.inject(HttpTestingController);
    f = TestBed.createComponent(AuditPage); f.detectChanges();
  });

  it('shows verification results and the limitations', () => {
    click('Verify audit log');
    ctl.expectOne('http://api.test/audit/verify').flush({ valid: true, rows: 7, broken_at_id: null, reason: '', head_hash: 'abc' });
    f.detectChanges();
    expect(el().textContent).toContain('Chain intact: 7 entries');
    expect(el().textContent).toContain('What this does not prove');
  });

  it('reports a broken chain with the entry id', () => {
    click('Verify audit log');
    ctl.expectOne('http://api.test/audit/verify').flush({ valid: false, rows: 7, broken_at_id: 4, reason: 'row was edited', head_hash: 'abc' });
    f.detectChanges();
    expect(el().textContent).toContain('Chain broken at entry 4');
  });

  it('only lists entries for the selected policy (scoped request)', () => {
    expect(el().textContent).toContain('Select a policy');
    const ws = TestBed.inject(WorkspaceStore);
    ws.policies.set([{ id: 'p1', name: 'Pol', pages: 1, chunks: 1, origin: 'sample', createdAt: '' }]); ws.select('p1'); f.detectChanges();
    click('Load entries');
    const req = ctl.expectOne((r) => r.url === 'http://api.test/audit');
    expect(req.request.params.get('policy_id')).toBe('p1');
    req.flush([{ id: 1, timestamp: 't', event: 'query', policy_id: 'p1', user_query: 'hello?', answer_summary: '', violation_count: 0, prev_hash: 'x', row_hash: 'abcdef1234567890' }]);
    f.detectChanges();
    expect(el().textContent).toContain('hello?');
  });
});
