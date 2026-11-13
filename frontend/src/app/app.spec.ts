import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';
import { App } from './app';
import { AppConfigService } from './core/app-config.service';
import { HealthResponse, ServerConfig } from './core/models';

const health = (mode: 'gemini' | 'offline'): HealthResponse => ({ status: 'ok', mode, embeddings: 'local-hash', kb_chunks: 134, warnings: [] });
const config = (demo: boolean): ServerConfig => ({
  demo_mode: demo, uploads_enabled: !demo, max_pdf_pages: 50, max_pdf_mb: 20, min_text_chars: 20, max_text_chars: 100000, max_question_chars: 1000, rate_limit_per_min: 0,
});

describe('App shell', () => {
  let ctl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    TestBed.inject(AppConfigService).apiBaseUrl.set('http://api.test');
    ctl = TestBed.inject(HttpTestingController);
  });

  function render() {
    const f = TestBed.createComponent(App);
    f.detectChanges();
    return f;
  }
  const text = (f: ReturnType<typeof render>) => (f.nativeElement as HTMLElement).textContent ?? '';

  it('shows the five primary destinations and a skip link', () => {
    const f = render();
    const links = Array.from((f.nativeElement as HTMLElement).querySelectorAll('nav a')).map((a) => a.textContent?.trim());
    expect(links).toEqual(['Dashboard', 'Policy workspace', 'Ask questions', 'Gap report', 'Audit']);
    expect((f.nativeElement as HTMLElement).querySelector('a.skip-link')?.getAttribute('href')).toBe('#main');
    ctl.expectOne('http://api.test/health'); ctl.expectOne('http://api.test/config');
  });

  it('reports offline mode and demo mode from the backend responses', () => {
    const f = render();
    ctl.expectOne('http://api.test/health').flush(health('offline'));
    ctl.expectOne('http://api.test/config').flush(config(true));
    f.detectChanges();
    expect(text(f)).toContain('Offline mode');
    expect(text(f)).toContain('Demo · samples only');
  });

  it('says "Gemini configured" (not "Gemini working") when a key is configured', () => {
    const f = render();
    ctl.expectOne('http://api.test/health').flush(health('gemini'));
    ctl.expectOne('http://api.test/config').flush(config(false));
    f.detectChanges();
    expect(text(f)).toContain('Gemini configured');
    expect(text(f)).not.toContain('Demo');
  });

  it('shows an unreachable state with a retry button when the API is down', () => {
    const f = render();
    ctl.expectOne('http://api.test/health').error(new ProgressEvent('error'));
    ctl.match('http://api.test/config').filter((r) => !r.cancelled).forEach((r) => r.error(new ProgressEvent('error')));
    f.detectChanges();
    expect(text(f)).toContain('API unreachable');
    expect(text(f)).toContain('Retry');
  });
});
