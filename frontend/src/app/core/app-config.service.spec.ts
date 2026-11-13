import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppConfigService } from './app-config.service';

describe('AppConfigService', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('reads apiBaseUrl from config.json and trims trailing slashes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ apiBaseUrl: 'https://api.example.org/' }) }));
    const svc = TestBed.inject(AppConfigService);
    await svc.load();
    expect(svc.apiBaseUrl()).toBe('https://api.example.org');
  });

  it('keeps the /api default when config.json is missing or invalid', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    const svc = TestBed.inject(AppConfigService);
    await svc.load();
    expect(svc.apiBaseUrl()).toBe('/api');
  });
});
