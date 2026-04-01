/**
 * Navigation & Shell Tests
 *
 * Verifies all sidebar nav links navigate correctly and every page
 * renders its primary heading (FR-016 — shell with all routes present).
 */
import { test, expect } from '@playwright/test';
import { setupCommonMocks } from './helpers/route-mocks';

test.describe('Shell Navigation (FR-016)', () => {
  test.beforeEach(async ({ page }) => {
    await setupCommonMocks(page);
  });

  test('renders the Contra logo and sidebar on initial load', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.logo-text')).toContainText('Contra');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('Run History link navigates to /runs and shows correct heading', async ({ page }) => {
    await page.goto('/');
    await page.locator('a[href="/runs"]').click();
    await expect(page).toHaveURL(/\/runs/);
    await expect(page.locator('h1')).toContainText('Run History');
  });

  test('Results link navigates to /results and shows correct heading', async ({ page }) => {
    await page.goto('/');
    await page.locator('a[href="/results"]').click();
    await expect(page).toHaveURL(/\/results/);
    await expect(page.locator('h1')).toContainText('Payment Records');
  });

  test('Settings link navigates to /settings and shows correct heading', async ({ page }) => {
    await page.goto('/');
    await page.locator('a[href="/settings"]').click();
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.locator('h1')).toContainText('LLM Settings');
  });

  test('Pipeline Monitor link navigates to /pipeline', async ({ page }) => {
    await page.goto('/');
    await page.locator('a[href="/pipeline"]').click();
    await expect(page).toHaveURL(/\/pipeline/);
  });

  test('active class applied to the current route link', async ({ page }) => {
    await page.goto('/runs');
    const activeLink = page.locator('a.active[href="/runs"]');
    await expect(activeLink).toBeVisible();
  });

  test('all six nav items are visible in the sidebar', async ({ page }) => {
    await page.goto('/');
    const navLinks = page.locator('.nav-list li a');
    await expect(navLinks).toHaveCount(7); // pipeline, activity, review, audit, runs, results, settings
  });

  test('direct URL navigation to /runs works without 404', async ({ page }) => {
    await page.goto('/runs');
    await expect(page.locator('h1')).toContainText('Run History');
    // No error page
    await expect(page.locator('body')).not.toContainText('404');
  });

  test('direct URL navigation to /results works without 404', async ({ page }) => {
    await page.goto('/results');
    await expect(page.locator('h1')).toContainText('Payment Records');
    await expect(page.locator('body')).not.toContainText('404');
  });
});
