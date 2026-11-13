import { Injectable, signal } from '@angular/core';

export interface RuntimeConfig {
  apiBaseUrl: string;
}

/**
 * Runtime configuration loaded from /config.json at startup, so the API address can be changed per
 * deployment without rebuilding. It must never contain secrets (the Gemini key lives only on the backend).
 */
@Injectable({ providedIn: 'root' })
export class AppConfigService {
  readonly apiBaseUrl = signal('/api');

  async load(): Promise<void> {
    try {
      const res = await fetch('config.json', { cache: 'no-store' });
      if (res.ok) {
        const cfg = (await res.json()) as Partial<RuntimeConfig>;
        if (typeof cfg.apiBaseUrl === 'string' && cfg.apiBaseUrl.length > 0) {
          this.apiBaseUrl.set(cfg.apiBaseUrl.replace(/\/+$/, ''));
        }
      }
    } catch {
      // keep the default (/api, handled by the dev proxy)
    }
  }
}
