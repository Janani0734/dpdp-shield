import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { ApiService } from './api.service';
import { AppConfigService } from './app-config.service';

describe('ApiService (HTTP integration with explicit mocks)', () => {
  let api: ApiService;
  let ctl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    TestBed.inject(AppConfigService).apiBaseUrl.set('http://api.test');
    api = TestBed.inject(ApiService);
    ctl = TestBed.inject(HttpTestingController);
  });

  it('calls the documented endpoints with the documented verbs', () => {
    api.health().subscribe();
    expect(ctl.expectOne({ method: 'GET', url: 'http://api.test/health' })).toBeTruthy();
    api.serverConfig().subscribe();
    ctl.expectOne({ method: 'GET', url: 'http://api.test/config' });
    api.samples().subscribe();
    ctl.expectOne({ method: 'GET', url: 'http://api.test/samples' });
    api.loadSample('bad_policy').subscribe();
    ctl.expectOne({ method: 'POST', url: 'http://api.test/samples/bad_policy/load' });
    api.analyze('abc123abc123').subscribe();
    ctl.expectOne({ method: 'POST', url: 'http://api.test/policies/abc123abc123/analyze' });
    api.deletePolicy('abc123abc123').subscribe();
    ctl.expectOne({ method: 'DELETE', url: 'http://api.test/policies/abc123abc123' });
    api.verifyAudit().subscribe();
    ctl.expectOne({ method: 'GET', url: 'http://api.test/audit/verify' });
    ctl.verify();
  });

  it('sends the query body with the backend field names', () => {
    api.query('abc123abc123', 'Is there a breach notification clause?').subscribe();
    const req = ctl.expectOne('http://api.test/query');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ policy_id: 'abc123abc123', question: 'Is there a breach notification clause?' });
  });

  it('uploads a PDF as multipart `file` and text as form field `text`', () => {
    const file = new File(['%PDF-1.4'], 'p.pdf', { type: 'application/pdf' });
    api.uploadPdf(file).subscribe();
    const pdf = ctl.expectOne('http://api.test/policies');
    expect((pdf.request.body as FormData).get('file')).toBeInstanceOf(File);
    api.uploadText('We collect your name for delivery.').subscribe();
    const txt = ctl.expectOne('http://api.test/policies');
    expect((txt.request.body as FormData).get('text')).toBe('We collect your name for delivery.');
  });

  it('scopes the audit request to a policy', () => {
    api.audit('abc123abc123', 25).subscribe();
    const req = ctl.expectOne((r) => r.url === 'http://api.test/audit');
    expect(req.request.params.get('policy_id')).toBe('abc123abc123');
    expect(req.request.params.get('limit')).toBe('25');
  });

  it('does NOT retry a failed non-idempotent request', () => {
    let errors = 0;
    api.analyze('abc123abc123').subscribe({ error: () => errors++ });
    ctl.expectOne('http://api.test/policies/abc123abc123/analyze').flush({ detail: 'x' }, { status: 503, statusText: 'Unavailable' });
    expect(errors).toBe(1);
    ctl.verify(); // would throw if a second request had been issued
  });

  it('url-encodes ids so they can never alter the path', () => {
    api.loadSample('../x').subscribe();
    ctl.expectOne('http://api.test/samples/..%2Fx/load');
  });
});
