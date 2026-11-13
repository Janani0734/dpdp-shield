import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AppConfigService } from './app-config.service';
import { Report } from './models';
import { WorkspaceStore } from './workspace.store';

const up = { policy_id: 'aaaaaaaaaaaa', name: 'Sample A', pages: 1, chunks: 4 };
const report = { policy_id: 'aaaaaaaaaaaa', policy_name: 'Sample A', generated_at: 'x', mode: 'offline', summary: { total_checks: 1, passed: 0, failed: 1, llm_extra_gaps: 0, by_severity: { high: 1, medium: 0, low: 0 }, highest_penalty_ceiling_crore: 0, note: '' }, rows: [], warnings: [], disclaimer: '' } as Report;

describe('WorkspaceStore', () => {
  let store: WorkspaceStore;
  let ctl: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    TestBed.inject(AppConfigService).apiBaseUrl.set('http://api.test');
    store = TestBed.inject(WorkspaceStore);
    ctl = TestBed.inject(HttpTestingController);
  });

  it('adds a sample, selects it, and ignores a second add while one is in flight', () => {
    store.addSample('bad_policy');
    store.addSample('good_policy');
    ctl.expectOne('http://api.test/samples/bad_policy/load').flush(up);
    ctl.verify();
    expect(store.selected()?.name).toBe('Sample A');
    expect(store.adding()).toBe(false);
  });

  it('re-choosing a loaded sample selects it instead of creating a duplicate policy', () => {
    store.addSample('bad_policy');
    ctl.expectOne('http://api.test/samples/bad_policy/load').flush(up);
    store.addSample('bad_policy');
    ctl.verify();
    expect(store.policies()).toHaveLength(1);
  });

  it('keeps the backend error message on a failed upload and adds nothing', () => {
    store.addText('short');
    ctl.expectOne('http://api.test/policies').flush({ detail: 'Text too short' }, { status: 400, statusText: 'Bad' });
    expect(store.error()?.message).toBe('Text too short');
    expect(store.policies()).toHaveLength(0);
  });

  it('caches the report per policy and drops it on delete', () => {
    store.addSample('bad_policy');
    ctl.expectOne('http://api.test/samples/bad_policy/load').flush(up);
    store.analyze('aaaaaaaaaaaa');
    ctl.expectOne('http://api.test/policies/aaaaaaaaaaaa/analyze').flush(report);
    expect(store.selectedReport()?.summary.failed).toBe(1);
    store.remove('aaaaaaaaaaaa');
    ctl.expectOne({ method: 'DELETE', url: 'http://api.test/policies/aaaaaaaaaaaa' }).flush({ deleted: 'aaaaaaaaaaaa' });
    expect(store.policies()).toHaveLength(0);
    expect(store.selectedReport()).toBeNull();
  });

  it('cancelling analysis stops waiting without issuing a retry', () => {
    store.analyze('aaaaaaaaaaaa');
    store.cancelAnalyze();
    expect(store.analyzingId()).toBeNull();
    expect(ctl.expectOne('http://api.test/policies/aaaaaaaaaaaa/analyze').cancelled).toBe(true);
    ctl.verify();
  });

  it('does not delete locally when the server call fails', () => {
    store.addSample('bad_policy');
    ctl.expectOne('http://api.test/samples/bad_policy/load').flush(up);
    store.remove('aaaaaaaaaaaa');
    ctl.expectOne('http://api.test/policies/aaaaaaaaaaaa').flush({}, { status: 500, statusText: 'x' });
    expect(store.policies()).toHaveLength(1);
    expect(store.error()?.kind).toBe('server');
  });
});
