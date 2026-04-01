import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright functional test configuration for Contra Angular frontend.
 *
 * Tests run against:
 *   Angular dev server → http://localhost:4200
 *   FastAPI backend    → http://localhost:8000
 *
 * Most tests intercept API calls via page.route() for determinism.
 * The 05-api-contract suite hits the real backend.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: process.env['CI'] ? 2 : 1,
  workers: 1,
  reporter: [
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['list'],
  ],
  use: {
    baseURL: 'http://localhost:4200',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
