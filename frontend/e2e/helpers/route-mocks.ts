/**
 * Reusable Playwright route interceptors.
 * Each helper installs a mock for a specific API resource.
 * Call before page.goto() to ensure requests are captured.
 */
import type { Page } from '@playwright/test';
import {
  API_BASE,
  BATCH_ID,
  MOCK_BATCH_DETAIL,
  MOCK_BATCH_RUNS,
  MOCK_PAYMENT_RECORDS,
  MOCK_RUN_STARTED,
  MOCK_SETTINGS,
  makeSseBody,
} from '../fixtures/mock-data';

// ── Individual resource mocks ──────────────────────────────────────────────

/**
 * Mock both GET and POST for /api/v1/runs.
 * Pass `postStatus` 409 or 400 to test error paths.
 */
export async function mockRunsEndpoint(
  page: Page,
  opts: {
    getRuns?: object[];
    postStatus?: number;
    postBody?: object;
  } = {}
): Promise<void> {
  const getRuns = opts.getRuns ?? MOCK_BATCH_RUNS;
  const postStatus = opts.postStatus ?? 202;
  const postBody = opts.postBody ?? MOCK_RUN_STARTED;

  await page.route(`${API_BASE}/runs`, async route => {
    const method = route.request().method();
    if (method === 'GET') {
      await route.fulfill({ json: getRuns });
    } else if (method === 'POST') {
      await route.fulfill({ status: postStatus, json: postBody });
    } else {
      await route.continue();
    }
  });
}

/** Mock GET /api/v1/runs/:batchId (detail endpoint). */
export async function mockRunDetailEndpoint(
  page: Page,
  batchId = BATCH_ID,
  detail = MOCK_BATCH_DETAIL
): Promise<void> {
  await page.route(`${API_BASE}/runs/${batchId}`, async route => {
    await route.fulfill({ json: detail });
  });
}

/**
 * Mock GET /api/v1/results.
 * Accepts a dynamic factory so tests can swap the response mid-test:
 *
 *   let result = allRecords;
 *   await mockResultsEndpoint(page, () => result);
 *   result = onlyValid;             // next request returns filtered data
 *   await page.locator('select').selectOption('Valid');
 */
export async function mockResultsEndpoint(
  page: Page,
  responseFactory: () => object[] = () => MOCK_PAYMENT_RECORDS
): Promise<void> {
  await page.route(`${API_BASE}/results**`, async route => {
    await route.fulfill({ json: responseFactory() });
  });
}

/**
 * Mock the SSE endpoint for a specific batch.
 * Returns all events in a single response body so EventSource processes them
 * immediately — sufficient for testing UI reactions without a real stream.
 */
export async function mockSseEndpoint(
  page: Page,
  batchId = BATCH_ID,
  body = makeSseBody(BATCH_ID)
): Promise<void> {
  await page.route(`${API_BASE}/runs/${batchId}/stream`, async route => {
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*',
      },
      body,
    });
  });
}

/** Mock GET and PUT /api/v1/settings/llm. */
export async function mockSettingsEndpoint(
  page: Page,
  settings = MOCK_SETTINGS
): Promise<void> {
  await page.route(`${API_BASE}/settings/llm`, async route => {
    const method = route.request().method();
    if (method === 'GET') {
      await route.fulfill({ json: settings });
    } else if (method === 'PUT') {
      const body = route.request().postDataJSON() ?? {};
      await route.fulfill({ json: { ...settings, ...body } });
    } else {
      await route.continue();
    }
  });
}

// ── Convenience composite ──────────────────────────────────────────────────

/**
 * Install the minimum set of mocks needed by every page that loads.
 * Prevents test errors from unhandled API requests.
 */
export async function setupCommonMocks(page: Page): Promise<void> {
  await mockSettingsEndpoint(page);
  await mockRunsEndpoint(page);
  await mockResultsEndpoint(page);
}
