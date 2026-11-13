import { expect, test } from '@playwright/test';

/** REAL backend (FastAPI, DEMO_MODE=true, no Gemini key, local embeddings). Does NOT exercise live Gemini. */
test.describe('REAL backend, offline + demo mode', () => {
  test('sample → analyze → report → ask → audit verify', async ({ page }) => {
    await page.goto('/workspace');
    await expect(page.getByText('Demo · samples only')).toBeVisible();
    await expect(page.locator('input[type=file]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Use this sample' }).first().click();
    await page.getByRole('button', { name: 'Run analysis' }).click();
    await page.getByRole('link', { name: 'View report' }).click({ timeout: 60_000 });
    await expect(page.getByRole('heading', { name: 'Gap report' })).toBeVisible();
    await expect(page.getByText(/Showing \d+ of \d+/)).toBeVisible();
    await page.getByLabel('Status').selectOption('fail');
    await expect(page.getByText('Potential gap').first()).toBeVisible();

    await page.getByRole('link', { name: 'Ask questions' }).click();
    await page.getByLabel('Your question').fill('Does the policy describe how to report a data breach?');
    await page.getByRole('button', { name: 'Ask' }).click();
    await expect(page.locator('article.turn')).toBeVisible({ timeout: 60_000 });

    await page.getByRole('link', { name: 'Audit' }).click();
    await page.getByRole('button', { name: 'Verify audit log' }).click();
    await expect(page.getByText(/valid|intact/i).first()).toBeVisible();
  });

  test('server rejects uploads in demo mode (not just the UI)', async ({ request }) => {
    const r = await request.post('http://127.0.0.1:8000/policies', { multipart: { text: 'x'.repeat(50) } });
    expect(r.status()).toBe(403);
  });
});
