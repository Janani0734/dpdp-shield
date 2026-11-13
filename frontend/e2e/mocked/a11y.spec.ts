import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { loadAndAnalyze, mockApi } from './fixtures';

/** Automated axe-core scan (WCAG 2.x A/AA rules). Catches a subset of issues only; it is not a full accessibility audit. */
for (const vp of [{ name: 'desktop', width: 1280, height: 800 }, { name: 'mobile', width: 375, height: 700 }]) {
  test(`axe: no A/AA violations on key pages (${vp.name}, mocked data)`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await mockApi(page, { config: { uploads_enabled: true, demo_mode: false } });
    const scan = async (label: string) => {
      const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
      expect(r.violations.map((v) => `${label}: ${v.id} (${v.nodes.length})`), label).toEqual([]);
    };
    await page.goto('/dashboard'); await scan('dashboard');
    await page.goto('/workspace'); await expect(page.getByText('Your own policy')).toBeVisible(); await scan('workspace');
    await loadAndAnalyze(page); await expect(page.getByText(/Showing/)).toBeVisible(); await scan('report');
    await page.getByRole('link', { name: 'Ask questions' }).click(); await scan('chat');
    await page.getByRole('link', { name: 'Audit' }).click(); await scan('audit');
  });
}

test('no horizontal scroll at 375px', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await mockApi(page);
  await loadAndAnalyze(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
