import { expect, test } from '@playwright/test'

test('shows the checkpoint console', async ({ page }) => {
  await page.route('**/api/v1/health', (route) => route.fulfill({ json: { status: 'ok', version: '0.1.0', registry_loaded: true, registry_snapshot_id: 'snapshot', credential_configured: false, active_benchmark_run_id: null } }))
  await page.route('**/api/v1/models', (route) => route.fulfill({ json: { schema_version: '1.0', snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com', models_sha256: 'abc', models: [] } }))
  await page.route('**/api/v1/routing/dashboard', (route) => route.fulfill({ json: { source_run_id: 'checkpoint-1-demo', source_dataset: 'openai/gsm8k', source_cells: 24, note: 'Offline replay.', strategies: [] } }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /one explicit policy/i })).toBeVisible()
  await expect(page.getByText('Key not configured')).toBeVisible()
})

test('keeps the primary console within a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/v1/health', (route) => route.fulfill({ json: { status: 'ok', version: '0.1.0', registry_loaded: true, registry_snapshot_id: 'snapshot', credential_configured: false, active_benchmark_run_id: null } }))
  await page.route('**/api/v1/models', (route) => route.fulfill({ json: { schema_version: '1.0', snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com', models_sha256: 'abc', models: [] } }))
  await page.route('**/api/v1/routing/dashboard', (route) => route.fulfill({ json: { source_run_id: 'checkpoint-1-demo', source_dataset: 'openai/gsm8k', source_cells: 24, note: 'Offline replay.', strategies: [] } }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /one explicit policy/i })).toBeVisible()
  const dimensions = await page.evaluate(() => ({ width: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width)
})
