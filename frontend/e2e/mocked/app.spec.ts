import { expect, test } from '@playwright/test';
import { loadAndAnalyze, mockApi, query, report } from './fixtures';

test.describe('MOCKED backend (UI behaviour only)', () => {
  test('sample → analysis → report with filters, wording and drafts', async ({ page }) => {
    await mockApi(page);
    await loadAndAnalyze(page);
    await expect(page.getByRole('heading', { name: 'Gap report' })).toBeVisible();
    await expect(page.getByText('potential gaps').first()).toBeVisible();
    // the only "compliant" wording allowed is the negated disclaimer; no badge may claim compliance or a violation
    await expect(page.getByText(/^(Compliant|Legally compliant|Violation|Legal violation)$/i)).toHaveCount(0);
    await expect(page.getByText('Showing 4 of 4')).toBeVisible();
    await page.getByLabel('Finding source').selectOption('llm');
    await expect(page.getByText('Showing 1 of 4')).toBeVisible();
    await expect(page.getByText('AI-suggested — verify')).toBeVisible();
    await page.getByLabel('Finding source').selectOption('all');
    await page.getByLabel('Status').selectOption('pass');
    await expect(page.getByText('Showing 1 of 4')).toBeVisible();
    await expect(page.getByText('We keep data for 1 year.')).toBeVisible();
    await page.getByLabel('Status').selectOption('fail');
    await page.getByLabel('Severity').selectOption('medium');
    await expect(page.getByText('Showing 2 of 4')).toBeVisible();
    await page.getByText(/Suggested draft/).first().click();
    await expect(page.getByText('A starting point only').first()).toBeVisible();
  });

  test('offline mode and demo mode are shown; uploads are not offered', async ({ page }) => {
    await mockApi(page);
    await page.goto('/workspace');
    await expect(page.getByText('Offline mode').first()).toBeVisible();
    await expect(page.getByText('Demo · samples only')).toBeVisible();
    await expect(page.getByText('Uploads are disabled on this server')).toBeVisible();
    await expect(page.locator('input[type=file]')).toHaveCount(0);
  });

  test('Gemini review skipped is surfaced from the backend warning', async ({ page }) => {
    await mockApi(page, { analyze: () => report({ mode: 'gemini', warnings: ['Gemini review skipped: quota'] }) });
    await loadAndAnalyze(page);
    await expect(page.getByText(/review was skipped/)).toBeVisible();
    await expect(page.getByText('Gemini review skipped: quota')).toBeVisible();
  });

  test('analysis API failure shows the backend message and no report; no automatic retry', async ({ page }) => {
    let calls = 0;
    await mockApi(page, { analyze: () => { calls++; return 503; } });
    await page.goto('/workspace');
    await page.getByRole('button', { name: 'Use this sample' }).first().click();
    await page.getByRole('button', { name: 'Run analysis' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Gemini unavailable' })).toBeVisible();
    await page.waitForTimeout(1500);
    expect(calls).toBe(1);
    await expect(page.getByRole('link', { name: 'View report' })).toHaveCount(0);
  });

  test('chat shows answer, citation metadata and fallback state; errors are reported', async ({ page }) => {
    let n = 0;
    await mockApi(page, { query: () => (++n === 1 ? query({ mode: 'gemini-fallback', warnings: ['Gemini call failed; rule-based answer shown.'] }) : 503) });
    await page.goto('/workspace');
    await page.getByRole('button', { name: 'Use this sample' }).first().click();
    await page.getByRole('link', { name: 'Ask questions' }).click();
    await page.getByLabel('Your question').fill('Is there a breach clause?');
    await page.getByRole('button', { name: 'Ask' }).click();
    await expect(page.getByText('does not state a breach-notification period')).toBeVisible();
    await expect(page.getByText('Rule 7').first()).toBeVisible();
    await expect(page.getByText(/p\.\s*12|page 12/i).first()).toBeVisible();
    await expect(page.getByText('Gemini call failed; rule-based answer shown.')).toBeVisible();
    await page.getByLabel('Your question').fill('Second?');
    await page.getByRole('button', { name: 'Ask' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Embedding service unavailable' })).toBeVisible();
  });

  test('audit verification shows the result and its limits', async ({ page }) => {
    await mockApi(page);
    await page.goto('/audit');
    await page.getByRole('button', { name: 'Verify audit log' }).click();
    await expect(page.getByRole('status').filter({ hasText: /valid|intact/i }).first()).toBeVisible();
  });

  test('audit verification failure is shown as broken', async ({ page }) => {
    await mockApi(page, { verify: { valid: false, rows: 3, broken_at_id: 2, reason: 'row was edited', head_hash: 'abc' } });
    await page.goto('/audit');
    await page.getByRole('button', { name: 'Verify audit log' }).click();
    await expect(page.getByText('row was edited')).toBeVisible();
  });

  test('API unreachable shows a retry affordance', async ({ page }) => {
    await page.route('**/api/**', (r) => r.abort());
    await page.goto('/dashboard');
    await expect(page.getByText('API unreachable')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  });

  test('skip link and keyboard focus are available', async ({ page }) => {
    await mockApi(page);
    await page.goto('/dashboard');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: /skip/i })).toBeFocused();
  });
});
