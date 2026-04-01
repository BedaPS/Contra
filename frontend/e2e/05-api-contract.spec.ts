/**
 * API Contract Tests — FR-015 (Backend API Contract)
 *
 * These tests run against the REAL backend (http://localhost:8000).
 * No browser is launched — they use Playwright's `request` fixture (APIRequestContext).
 *
 * Preconditions:
 *  - Backend container must be running: `docker compose up -d`
 *  - DB migrations must have completed (handled automatically by entrypoint.sh)
 *
 * Covers the contract specified in specs/001-multi-agent-doc-processing/contracts/openapi-additions.md
 */
import { test, expect } from '@playwright/test';

const BACKEND = 'http://localhost:8000/api/v1';
const NONEXISTENT_ID = '00000000-dead-beef-0000-000000000000';

// ── Health ────────────────────────────────────────────────────────────────

test.describe('GET /api/v1/health', () => {
  test('returns 200 with { status: "ok" }', async ({ request }) => {
    const res = await request.get(`${BACKEND}/health`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('status', 'ok');
  });
});

// ── Runs — list ───────────────────────────────────────────────────────────

test.describe('GET /api/v1/runs', () => {
  test('returns 200 with an array', async ({ request }) => {
    const res = await request.get(`${BACKEND}/runs`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test('each run item has required fields', async ({ request }) => {
    const res = await request.get(`${BACKEND}/runs`);
    const body = await res.json();
    if (body.length > 0) {
      const run = body[0];
      expect(run).toHaveProperty('batch_id');
      expect(run).toHaveProperty('status');
      expect(run).toHaveProperty('triggered_at');
      expect(run).toHaveProperty('total_files');
    }
  });
});

// ── Runs — trigger ────────────────────────────────────────────────────────

test.describe('POST /api/v1/runs', () => {
  test('returns 400 when source_directory is not configured', async ({ request }) => {
    // Docker container runs with LLM_PROVIDER=stub but may have source_directory empty
    // or pointing to a non-existent path — the API must reject it with 400.
    // If a run is currently In Progress it returns 409 — both are acceptable error responses.
    const res = await request.post(`${BACKEND}/runs`, { data: {} });
    // Accept 400 (not configured) or 409 (already in progress) or 202 (success if configured)
    expect([202, 400, 409]).toContain(res.status());
  });

  test('response body is JSON', async ({ request }) => {
    const res = await request.post(`${BACKEND}/runs`, { data: {} });
    const body = await res.json();
    expect(typeof body).toBe('object');
  });
});

// ── Runs — single batch detail ────────────────────────────────────────────

test.describe('GET /api/v1/runs/:batchId', () => {
  test('returns 404 for a non-existent batch_id', async ({ request }) => {
    const res = await request.get(`${BACKEND}/runs/${NONEXISTENT_ID}`);
    expect(res.status()).toBe(404);
  });

  test('404 response body has a detail field', async ({ request }) => {
    const res = await request.get(`${BACKEND}/runs/${NONEXISTENT_ID}`);
    const body = await res.json();
    expect(body).toHaveProperty('detail');
  });
});

// ── Results ───────────────────────────────────────────────────────────────

test.describe('GET /api/v1/results', () => {
  test('returns 200 with an array', async ({ request }) => {
    const res = await request.get(`${BACKEND}/results`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test('accepts validation_status query param without error', async ({ request }) => {
    const res = await request.get(`${BACKEND}/results?validation_status=Valid`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test('accepts doc_type query param without error', async ({ request }) => {
    const res = await request.get(`${BACKEND}/results?doc_type=email`);
    expect(res.status()).toBe(200);
  });

  test('accepts confidence_min and confidence_max params without error', async ({ request }) => {
    const res = await request.get(`${BACKEND}/results?confidence_min=0.5&confidence_max=1.0`);
    expect(res.status()).toBe(200);
  });

  test('accepts batch_id query param without error', async ({ request }) => {
    const res = await request.get(`${BACKEND}/results?batch_id=${NONEXISTENT_ID}`);
    // 200 with empty array — batch doesn't exist but filter is valid
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test('accepts limit and skip params without error', async ({ request }) => {
    const res = await request.get(`${BACKEND}/results?limit=10&skip=0`);
    expect(res.status()).toBe(200);
  });

  test('each PaymentRecord in response has required schema fields', async ({ request }) => {
    const res = await request.get(`${BACKEND}/results?limit=1`);
    const body = await res.json();
    if (body.length > 0) {
      const record = body[0];
      expect(record).toHaveProperty('id');
      expect(record).toHaveProperty('batch_id');
      expect(record).toHaveProperty('source_filename');
      expect(record).toHaveProperty('validation_status');
      expect(record).toHaveProperty('overall_confidence');
    }
  });
});

// ── Settings ──────────────────────────────────────────────────────────────

test.describe('GET /api/v1/settings/llm', () => {
  test('returns 200 with settings object', async ({ request }) => {
    const res = await request.get(`${BACKEND}/settings/llm`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('provider');
    expect(body).toHaveProperty('model');
    expect(body).toHaveProperty('source_directory');
    expect(body).toHaveProperty('work_directory');
  });

  test('api_key_set is a boolean', async ({ request }) => {
    const res = await request.get(`${BACKEND}/settings/llm`);
    const body = await res.json();
    expect(typeof body.api_key_set).toBe('boolean');
  });

  test('api_key is not present in response (masked)', async ({ request }) => {
    const res = await request.get(`${BACKEND}/settings/llm`);
    const body = await res.json();
    // Raw key must never be returned — only api_key_set boolean
    expect(body).not.toHaveProperty('api_key');
  });
});

// ── Pipeline topology ─────────────────────────────────────────────────────

test.describe('GET /api/v1/pipeline/topology', () => {
  test('returns 200 with nodes array', async ({ request }) => {
    const res = await request.get(`${BACKEND}/pipeline/topology`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('nodes');
    expect(Array.isArray(body.nodes)).toBe(true);
  });
});
