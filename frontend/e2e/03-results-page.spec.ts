/**
 * Results Page Tests — US2 (Review Results) + FR-017 (Filtering)
 *
 * Covers:
 *  - FR-006a: PaymentRecord table with all required columns
 *  - FR-017: Filter panel — validation status, doc type, confidence range, clear
 *  - US2 Scenario 3: Results tab shows records for a given batch
 *  - US2 Scenario 4: Filter by validation status
 *  - US2 Scenario 5: Row expansion shows per-field confidence scores
 */
import { test, expect } from '@playwright/test';
import {
  API_BASE,
  BATCH_ID,
  MOCK_PAYMENT_RECORDS,
} from './fixtures/mock-data';
import {
  mockRunsEndpoint,
  mockResultsEndpoint,
  mockSettingsEndpoint,
} from './helpers/route-mocks';

// ── Filter panel ──────────────────────────────────────────────────────────

test.describe('Results Page — filter panel (FR-017)', () => {
  test.beforeEach(async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/results');
  });

  test('displays the filter panel with four filter groups', async ({ page }) => {
    const groups = page.locator('.filter-group');
    await expect(groups).toHaveCount(4);
  });

  test('first filter group is "Validation Status" with a select', async ({ page }) => {
    const group = page.locator('.filter-group').nth(0);
    await expect(group.locator('label')).toContainText('Validation Status');
    await expect(group.locator('select')).toBeVisible();
  });

  test('second filter group is "Doc Type" with a select', async ({ page }) => {
    const group = page.locator('.filter-group').nth(1);
    await expect(group.locator('label')).toContainText('Doc Type');
    await expect(group.locator('select')).toBeVisible();
  });

  test('Validation Status select has expected options', async ({ page }) => {
    const sel = page.locator('.filter-group').nth(0).locator('select');
    // Use allTextContents() — <option> elements inside a closed <select> are in the DOM
    // but Playwright (correctly) reports them as hidden per browser visibility rules.
    const optionTexts = await sel.locator('option').allTextContents();
    expect(optionTexts.some(t => t.trim() === 'All')).toBeTruthy();
    expect(optionTexts.some(t => t.includes('Valid'))).toBeTruthy();
    expect(optionTexts.some(t => t.includes('Review Required'))).toBeTruthy();
    expect(optionTexts.some(t => t.includes('Extraction Failed'))).toBeTruthy();
  });

  test('"Clear Filters" button is present', async ({ page }) => {
    await expect(page.locator('.btn-clear')).toBeVisible();
    await expect(page.locator('.btn-clear')).toContainText('Clear Filters');
  });
});

// ── Table structure ───────────────────────────────────────────────────────

test.describe('Results Page — table columns (FR-006a)', () => {
  test.beforeEach(async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/results');
  });

  test('renders the Payment Records heading', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Payment Records');
  });

  test('table has 10 column headers', async ({ page }) => {
    const headers = page.locator('.results-table th');
    await expect(headers).toHaveCount(10);
  });

  test('column headers include all required field names', async ({ page }) => {
    const headers = page.locator('.results-table th');
    const texts = await headers.allTextContents();
    const joined = texts.join(' ');
    expect(joined).toContain('Customer');
    expect(joined).toContain('Payee');
    expect(joined).toContain('Amount');
    expect(joined).toContain('Currency');
    expect(joined).toContain('Status');
    expect(joined).toContain('Confidence');
    expect(joined).toContain('Doc Type');
    expect(joined).toContain('Source File');
  });

  test('renders one row per payment record', async ({ page }) => {
    await expect(page.locator('.result-row')).toHaveCount(MOCK_PAYMENT_RECORDS.length);
  });

  test('shows empty-state when no records match filters', async ({ page }) => {
    await page.unroute(`${API_BASE}/results**`);
    await mockResultsEndpoint(page, () => []);
    await page.reload();
    await expect(page.locator('.empty-state')).toBeVisible();
    await expect(page.locator('.empty-state')).toContainText('No records found');
  });
});

// ── Status chip colours ───────────────────────────────────────────────────

test.describe('Results Page — status chip CSS classes', () => {
  test.beforeEach(async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/results');
  });

  test('Valid record has .row-valid row class and green .status-valid chip', async ({ page }) => {
    const validRow = page.locator('.result-row.row-valid').first();
    await expect(validRow).toBeVisible();
    const chip = validRow.locator('.status-chip');
    await expect(chip).toHaveClass(/status-valid/);
    await expect(chip).toContainText('Valid');
  });

  test('Review Required record has .row-review class and amber .status-review chip', async ({ page }) => {
    const reviewRow = page.locator('.result-row.row-review').first();
    await expect(reviewRow).toBeVisible();
    const chip = reviewRow.locator('.status-chip');
    await expect(chip).toHaveClass(/status-review/);
    await expect(chip).toContainText('Review Required');
  });

  test('Extraction Failed record has .row-failed class and red .status-failed chip', async ({ page }) => {
    const failedRow = page.locator('.result-row.row-failed').first();
    await expect(failedRow).toBeVisible();
    const chip = failedRow.locator('.status-chip');
    await expect(chip).toHaveClass(/status-failed/);
    await expect(chip).toContainText('Extraction Failed');
  });

  test('ACME Corporation record displays customer name in first column', async ({ page }) => {
    const row = page.locator('.result-row').nth(0);
    await expect(row.locator('td').first()).toContainText('ACME Corporation');
  });

  test('confidence is displayed as percentage', async ({ page }) => {
    const validRow = page.locator('.result-row').nth(0);
    // overall_confidence=0.97 → "97%"
    const cells = await validRow.locator('td').allTextContents();
    const confidenceCell = cells.find(t => t.includes('%'));
    expect(confidenceCell).toBeDefined();
    expect(confidenceCell).toContain('97%');
  });
});

// ── Filtering (FR-017) ────────────────────────────────────────────────────

test.describe('Results Page — filtering (FR-017, US2 Scenario 4)', () => {
  test('filtering by Validation Status sends param in API request', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);

    let currentRecords = MOCK_PAYMENT_RECORDS.slice();
    await mockResultsEndpoint(page, () => currentRecords);
    await page.goto('/results');

    // Now change the response so only Valid records come back
    currentRecords = MOCK_PAYMENT_RECORDS.filter(r => r.validation_status === 'Valid');

    // Listen for the filtered request
    const [filteredReq] = await Promise.all([
      page.waitForRequest(req =>
        req.url().includes('/results') && req.url().includes('validation_status=Valid')
      ),
      page.locator('.filter-group').nth(0).locator('select').selectOption('Valid'),
    ]);

    expect(filteredReq.url()).toContain('validation_status=Valid');
    // UI should show only the 1 valid record
    await expect(page.locator('.result-row')).toHaveCount(1);
  });

  test('filtering by Doc Type sends param in API request', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);

    let currentRecords = MOCK_PAYMENT_RECORDS.slice();
    await mockResultsEndpoint(page, () => currentRecords);
    await page.goto('/results');

    currentRecords = MOCK_PAYMENT_RECORDS.filter(r => r.doc_type === 'email');

    const [filteredReq] = await Promise.all([
      page.waitForRequest(req =>
        req.url().includes('/results') && req.url().includes('doc_type=email')
      ),
      page.locator('.filter-group').nth(1).locator('select').selectOption('email'),
    ]);

    expect(filteredReq.url()).toContain('doc_type=email');
    await expect(page.locator('.result-row')).toHaveCount(1);
  });

  test('clear filters resets selects and calls API without filter params', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);

    let currentRecords = MOCK_PAYMENT_RECORDS.slice();
    await mockResultsEndpoint(page, () => currentRecords);
    await page.goto('/results');

    // Apply a filter first
    currentRecords = MOCK_PAYMENT_RECORDS.filter(r => r.validation_status === 'Valid');
    await page.locator('.filter-group').nth(0).locator('select').selectOption('Valid');
    await expect(page.locator('.result-row')).toHaveCount(1);

    // Now clear — restore full response
    currentRecords = MOCK_PAYMENT_RECORDS.slice();
    const [clearReq] = await Promise.all([
      page.waitForRequest(req =>
        req.url().includes('/results') && !req.url().includes('validation_status')
      ),
      page.locator('.btn-clear').click(),
    ]);

    expect(clearReq.url()).not.toContain('validation_status');
    await expect(page.locator('.result-row')).toHaveCount(MOCK_PAYMENT_RECORDS.length);
    // Select is reset to "All"
    await expect(page.locator('.filter-group').nth(0).locator('select')).toHaveValue('');
  });
});

// ── Row expansion (US2 Scenario 5) ───────────────────────────────────────

test.describe('Results Page — row expansion (US2 Scenario 5)', () => {
  test.beforeEach(async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/results');
  });

  test('clicking a row reveals the per-field confidence section', async ({ page }) => {
    // Click the first row (ACME — has confidence scores)
    await page.locator('.result-row').nth(0).click();
    await expect(page.locator('.expand-row')).toBeVisible();
    await expect(page.locator('.confidence-grid')).toBeVisible();
    await expect(page.locator('.confidence-grid strong')).toContainText('Per-field Confidence Scores');
  });

  test('expanded row shows individual field score items', async ({ page }) => {
    await page.locator('.result-row').nth(0).click();
    // Mock data has 3 fields: customer_name, amount_paid, payment_date
    await expect(page.locator('.score-item')).toHaveCount(3);
  });

  test('clicking the same row again collapses the expansion', async ({ page }) => {
    await page.locator('.result-row').nth(0).click();
    await expect(page.locator('.expand-row')).toBeVisible();

    await page.locator('.result-row').nth(0).click();
    await expect(page.locator('.expand-row')).not.toBeVisible();
  });

  test('Extraction Failed row with empty confidence_scores shows no score items', async ({ page }) => {
    // Click the email row (3rd, Extraction Failed, confidence_scores={})
    await page.locator('.result-row').nth(2).click();
    const expandRow = page.locator('.expand-row');
    await expect(expandRow).toBeVisible();
    // No score-item elements because confidence_scores is empty
    await expect(page.locator('.score-item')).toHaveCount(0);
  });
});

// ── Batch pre-filter from query param (US2 Scenario 3) ───────────────────

test.describe('Results Page — batch_id query param (US2 Scenario 3)', () => {
  test('navigating with ?batch_id sends it in the API request', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);

    const [req] = await Promise.all([
      page.waitForRequest(req =>
        req.url().includes('/results') && req.url().includes(`batch_id=${BATCH_ID}`)
      ),
      page.goto(`/results?batch_id=${BATCH_ID}`),
    ]);

    expect(req.url()).toContain(`batch_id=${BATCH_ID}`);
  });

  test('batch subtitle is shown when batch_id query param is present', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto(`/results?batch_id=${BATCH_ID}`);
    // Subtitle shows "Batch: <batchId>"
    await expect(page.locator('.subtitle')).toContainText('Batch');
    await expect(page.locator('.subtitle')).toContainText(BATCH_ID.slice(0, 8));
  });

  test('without batch_id query param shows "All batches" subtitle', async ({ page }) => {
    await mockSettingsEndpoint(page);
    await mockRunsEndpoint(page);
    await mockResultsEndpoint(page);
    await page.goto('/results');
    await expect(page.locator('.subtitle')).toContainText('All batches');
  });
});
