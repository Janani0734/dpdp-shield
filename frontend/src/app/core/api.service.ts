import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { AppConfigService } from './app-config.service';
import {
  AuditRow,
  AuditVerifyResult,
  HealthResponse,
  PolicyUploadResponse,
  QueryResult,
  Report,
  SampleInfo,
  ServerConfig,
} from './models';

/**
 * Thin typed wrapper over the FastAPI backend. Deliberately has NO retry logic: uploads, analysis and
 * queries write audit rows and may spend LLM quota, so they must only ever run on an explicit user action.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly cfg = inject(AppConfigService);

  private url(path: string): string {
    return `${this.cfg.apiBaseUrl()}${path}`;
  }

  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(this.url('/health'));
  }

  serverConfig(): Observable<ServerConfig> {
    return this.http.get<ServerConfig>(this.url('/config'));
  }

  samples(): Observable<SampleInfo[]> {
    return this.http.get<SampleInfo[]>(this.url('/samples'));
  }

  loadSample(id: string): Observable<PolicyUploadResponse> {
    return this.http.post<PolicyUploadResponse>(this.url(`/samples/${encodeURIComponent(id)}/load`), null);
  }

  uploadPdf(file: File): Observable<PolicyUploadResponse> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http.post<PolicyUploadResponse>(this.url('/policies'), body);
  }

  uploadText(text: string): Observable<PolicyUploadResponse> {
    const body = new FormData();
    body.append('text', text);
    return this.http.post<PolicyUploadResponse>(this.url('/policies'), body);
  }

  analyze(policyId: string): Observable<Report> {
    return this.http.post<Report>(this.url(`/policies/${encodeURIComponent(policyId)}/analyze`), null);
  }

  deletePolicy(policyId: string): Observable<{ deleted: string }> {
    return this.http.delete<{ deleted: string }>(this.url(`/policies/${encodeURIComponent(policyId)}`));
  }

  query(policyId: string, question: string): Observable<QueryResult> {
    return this.http.post<QueryResult>(this.url('/query'), { policy_id: policyId, question });
  }

  audit(policyId: string, limit = 50): Observable<AuditRow[]> {
    const params = new HttpParams().set('policy_id', policyId).set('limit', limit);
    return this.http.get<AuditRow[]>(this.url('/audit'), { params });
  }

  verifyAudit(): Observable<AuditVerifyResult> {
    return this.http.get<AuditVerifyResult>(this.url('/audit/verify'));
  }
}
