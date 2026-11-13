import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, Subscription } from 'rxjs';
import { ApiError, toApiError } from './api-error';
import { ApiService } from './api.service';
import { PolicyUploadResponse, Report, SessionPolicy } from './models';

/**
 * Session-only state: policies created in this browser tab and their last report. The backend has no
 * list/get-report endpoint, so nothing here survives a reload and nothing is invented client-side.
 * Every network call is started by an explicit user action; there are no retries.
 */
@Injectable({ providedIn: 'root' })
export class WorkspaceStore {
  private readonly api = inject(ApiService);
  private analyzeSub: Subscription | null = null;

  readonly policies = signal<SessionPolicy[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly reports = signal<Record<string, Report>>({});
  readonly adding = signal(false);
  readonly analyzingId = signal<string | null>(null);
  readonly deletingId = signal<string | null>(null);
  readonly error = signal<ApiError | null>(null);

  readonly selected = computed(() => this.policies().find((p) => p.id === this.selectedId()) ?? null);
  readonly selectedReport = computed(() => {
    const id = this.selectedId();
    return id ? (this.reports()[id] ?? null) : null;
  });
  readonly analyzedReports = computed(() => Object.values(this.reports()));

  select(id: string): void {
    this.selectedId.set(id);
  }

  clearError(): void {
    this.error.set(null);
  }

  private add(obs: Observable<PolicyUploadResponse>, origin: SessionPolicy['origin'], sampleId?: string): void {
    if (this.adding()) return;
    this.adding.set(true);
    this.error.set(null);
    obs.subscribe({
      next: (r) => {
        const p: SessionPolicy = { id: r.policy_id, name: r.name, pages: r.pages, chunks: r.chunks, origin, sampleId, createdAt: new Date().toISOString() };
        this.policies.update((l) => [p, ...l.filter((x) => x.id !== p.id)]);
        this.selectedId.set(p.id);
        this.adding.set(false);
      },
      error: (e) => { this.error.set(toApiError(e)); this.adding.set(false); },
    });
  }

  addSample(id: string): void {
    const existing = this.policies().find((p) => p.sampleId === id);
    if (existing) { this.selectedId.set(existing.id); return; }
    this.add(this.api.loadSample(id), 'sample', id);
  }
  addPdf(file: File): void { this.add(this.api.uploadPdf(file), 'pdf'); }
  addText(text: string): void { this.add(this.api.uploadText(text), 'text'); }

  analyze(id: string): void {
    if (this.analyzingId()) return;
    this.analyzingId.set(id);
    this.error.set(null);
    this.analyzeSub = this.api.analyze(id).subscribe({
      next: (r) => { this.reports.update((m) => ({ ...m, [id]: r })); this.analyzingId.set(null); },
      error: (e) => { this.error.set(toApiError(e)); this.analyzingId.set(null); },
    });
  }

  /** Stops waiting for the response. The server may still finish the request; nothing is retried. */
  cancelAnalyze(): void {
    this.analyzeSub?.unsubscribe();
    this.analyzeSub = null;
    this.analyzingId.set(null);
  }

  remove(id: string): void {
    if (this.deletingId()) return;
    this.deletingId.set(id);
    this.error.set(null);
    this.api.deletePolicy(id).subscribe({
      next: () => {
        this.policies.update((l) => l.filter((p) => p.id !== id));
        this.reports.update((m) => { const rest = { ...m }; delete rest[id]; return rest; });
        if (this.selectedId() === id) this.selectedId.set(this.policies()[0]?.id ?? null);
        this.deletingId.set(null);
      },
      error: (e) => { this.error.set(toApiError(e)); this.deletingId.set(null); },
    });
  }
}
