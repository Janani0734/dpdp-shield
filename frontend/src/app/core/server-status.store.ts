import { Injectable, computed, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';
import { ApiError, toApiError } from './api-error';
import { ApiService } from './api.service';
import { HealthResponse, ServerConfig } from './models';

export type ServerState = 'loading' | 'ready' | 'error';

/** What the backend reports about itself (read-only GETs; safe to repeat). */
@Injectable({ providedIn: 'root' })
export class ServerStatusStore {
  private readonly api = inject(ApiService);

  readonly state = signal<ServerState>('loading');
  readonly health = signal<HealthResponse | null>(null);
  readonly config = signal<ServerConfig | null>(null);
  readonly error = signal<ApiError | null>(null);

  readonly uploadsEnabled = computed(() => this.config()?.uploads_enabled ?? false);
  readonly demoMode = computed(() => this.config()?.demo_mode ?? false);

  load(): void {
    this.state.set('loading');
    forkJoin({ health: this.api.health(), config: this.api.serverConfig() }).subscribe({
      next: ({ health, config }) => {
        this.health.set(health);
        this.config.set(config);
        this.error.set(null);
        this.state.set('ready');
      },
      error: (e: unknown) => {
        this.error.set(toApiError(e));
        this.state.set('error');
      },
    });
  }
}
