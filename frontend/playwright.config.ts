import { defineConfig } from '@playwright/test';

/**
 * Two kinds of e2e tests, kept apart on purpose:
 *  - `mocked`: the browser's /api calls are intercepted with fixtures (e2e/mocked/*). They test the UI, not the backend.
 *  - `real-offline`: talk to a real FastAPI process started below with DEMO_MODE=true and NO Gemini key (e2e/real/*).
 * Live-Gemini behaviour is NOT covered by either; see frontend/README.md.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4200',
    trace: 'retain-on-failure',
    // Only for environments whose preinstalled Chromium differs from this Playwright's pinned build.
    launchOptions: process.env['PW_CHROMIUM_PATH'] ? { executablePath: process.env['PW_CHROMIUM_PATH'] } : {},
  },
  projects: [
    { name: 'mocked', testDir: './e2e/mocked' },
    { name: 'real-offline', testDir: './e2e/real' },
  ],
  webServer: [
    {
      command: 'npx ng serve --host 127.0.0.1 --port 4200',
      url: 'http://127.0.0.1:4200',
      reuseExistingServer: true,
      timeout: 180_000,
    },
    {
      command: 'python3 -m uvicorn dpdp_shield.api:app --host 127.0.0.1 --port 8000',
      cwd: '..',
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: true,
      timeout: 240_000,
      env: { GEMINI_API_KEY: '', DEMO_MODE: 'true', DATA_DIR: '/tmp/dpdp-e2e-data', EMBEDDINGS_BACKEND: 'local' },
    },
  ],
});
