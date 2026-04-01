/**
 * Settings Page Tests — FR-001 (Directory Settings), FR-013 (Provider Config)
 *
 * Covers:
 *  - FR-001: source_directory and work_directory configuration fields
 *  - FR-013: LLM provider dropdown selection
 *  - Save settings triggers PUT /api/v1/settings/llm
 *  - Existing settings are populated on load
 */
import { test, expect } from '@playwright/test';
import { API_BASE, MOCK_SETTINGS } from './fixtures/mock-data';
import {
  mockRunsEndpoint,
  mockResultsEndpoint,
  mockSettingsEndpoint,
} from './helpers/route-mocks';

test.describe('Settings Page — structure and load (FR-001, FR-013)', () => {
  test.beforeEach(async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/settings');
  });

  test('shows the LLM Settings heading', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('LLM Settings');
  });

  test('Provider dropdown is visible with expected options (FR-013)', async ({ page }) => {
    const providerSelect = page.locator('#provider');
    await expect(providerSelect).toBeVisible();
    // <option> elements in a closed <select> are DOM-present but not visible per browser rules;
    // use allTextContents() to verify options exist without a visibility assertion.
    const optionValues = await providerSelect.locator('option').evaluateAll(
      (els: HTMLOptionElement[]) => els.map(el => el.value)
    );
    expect(optionValues).toContain('gemini');
    expect(optionValues).toContain('openai');
    expect(optionValues).toContain('anthropic');
    expect(optionValues).toContain('local');
    expect(optionValues).toContain('stub');
  });

  test('loads current provider from API and populates the dropdown', async ({ page }) => {
    // MOCK_SETTINGS.provider = 'stub'
    await expect(page.locator('#provider')).toHaveValue('stub');
  });

  test('Source Directory field is visible and enabled (FR-001)', async ({ page }) => {
    const input = page.locator('#sourceDirectory');
    await expect(input).toBeVisible();
    await expect(input).toBeEnabled();
  });

  test('Work Directory field is visible and enabled (FR-001)', async ({ page }) => {
    const input = page.locator('#workDirectory');
    await expect(input).toBeVisible();
    await expect(input).toBeEnabled();
  });

  test('Review Directory field is visible', async ({ page }) => {
    await expect(page.locator('#reviewDirectory')).toBeVisible();
  });

  test('"Save Settings" button is visible', async ({ page }) => {
    await expect(page.locator('button.btn-primary')).toBeVisible();
    await expect(page.locator('button.btn-primary')).toContainText('Save Settings');
  });

  test('"Directory Settings" section heading is visible', async ({ page }) => {
    await expect(page.locator('.section-title')).toContainText('Directory Settings');
  });
});

test.describe('Settings Page — save settings', () => {
  test('clicking Save Settings sends PUT to /api/v1/settings/llm', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/settings');

    const [putRequest] = await Promise.all([
      page.waitForRequest(req =>
        req.url().includes('/settings/llm') && req.method() === 'PUT'
      ),
      page.locator('button.btn-primary').click(),
    ]);

    expect(putRequest.method()).toBe('PUT');
    expect(putRequest.url()).toContain('/api/v1/settings/llm');
  });

  test('shows success status message after save', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/settings');
    await page.locator('button.btn-primary').click();
    await expect(page.locator('.status')).toContainText('saved', { timeout: 5000 });
  });

  test('PUT request body includes source_directory field', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/settings');

    // Update source directory
    await page.locator('#sourceDirectory').fill('/new/source/path');

    const [putRequest] = await Promise.all([
      page.waitForRequest(req =>
        req.url().includes('/settings/llm') && req.method() === 'PUT'
      ),
      page.locator('button.btn-primary').click(),
    ]);

    const body = putRequest.postDataJSON();
    expect(body).toHaveProperty('source_directory', '/new/source/path');
  });

  test('PUT request body includes work_directory field', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/settings');

    await page.locator('#workDirectory').fill('/new/work/path');

    const [putRequest] = await Promise.all([
      page.waitForRequest(req =>
        req.url().includes('/settings/llm') && req.method() === 'PUT'
      ),
      page.locator('button.btn-primary').click(),
    ]);

    const body = putRequest.postDataJSON();
    expect(body).toHaveProperty('work_directory', '/new/work/path');
  });
});

test.describe('Settings Page — provider change', () => {
  test('switching to non-stub provider reveals API Key field', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/settings');

    // Switch from stub to gemini
    await page.locator('#provider').selectOption('gemini');
    // API key input should now appear
    await expect(page.locator('#apiKey')).toBeVisible();
  });

  test('switching back to stub hides API key and model fields', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/settings');

    // Switch to openai then back to stub
    await page.locator('#provider').selectOption('openai');
    await expect(page.locator('#apiKey')).toBeVisible();

    await page.locator('#provider').selectOption('stub');
    await expect(page.locator('#apiKey')).not.toBeVisible();
  });
});
