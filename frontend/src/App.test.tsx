import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

const health = { status: 'ok', version: '0.1.0', registry_loaded: true, registry_snapshot_id: 'snapshot', credential_configured: false, active_benchmark_run_id: null }
const model = (id: string, context: number) => ({ id, display_name: id, provider: id.split('/')[0], context_length: context, pricing: { prompt_per_token: '0', completion_per_token: '0' }, input_modalities: ['text'], output_modalities: ['text'], supported_parameters: [], capabilities: { tools: true, structured_output: true }, enabled: true, snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com' })
const dashboard = { pool: 'paid', source_run_id: 'checkpoint-2-paid-demo', source_dataset: 'openai/gsm8k', source_cells: 36, model_ids: [], note: 'Offline replay selects from the same saved matrix.', strategies: [], prompts: [] }
const decision = { strategy_id: 'rule_based_v1', pool: 'baseline', priority: 'quality', min_context_tokens: 1, selected_model_id: 'nvidia/nemotron:free', eligible_model_ids: ['google/gemma:free', 'nvidia/nemotron:free'], task_signals: ['general'], reason: 'Quality priority selects the designated stronger baseline.' }
const validation = { strategy_id: 'rule_based_v1', registry_snapshot_id: 'snapshot', passed: true, passed_cases: 5, total_cases: 5, cases: [] }

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('renders checkpoint status and keeps live actions unavailable without a key', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.endsWith('/health')
      ? health
      : url.includes('/routing/dashboard')
        ? dashboard
        : url.includes('/routing/validation')
          ? validation
        : { schema_version: '1.0', snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com', models_sha256: 'abc', models: [model('google/gemma:free', 262144), model('nvidia/nemotron:free', 1000000)] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>)
  expect(await screen.findByText('Adaptive LLM Router')).toBeInTheDocument()
  expect(screen.getByText('Key not configured')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /route prompt/i })).toBeDisabled()
  expect(screen.getByRole('button', { name: /preview decision/i })).toBeEnabled()
  expect(await screen.findByText(/same saved matrix/i)).toBeInTheDocument()
  expect(await screen.findByText('5/5 passed')).toBeInTheDocument()
})

test('previews a different route priority without a provider credential', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.endsWith('/health')
      ? health
      : url.includes('/routing/dashboard')
        ? dashboard
        : url.includes('/routing/validation')
          ? validation
          : url.endsWith('/routing/decisions')
            ? decision
            : { schema_version: '1.0', snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com', models_sha256: 'abc', models: [model('google/gemma:free', 262144), model('nvidia/nemotron:free', 1000000)] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
  const user = userEvent.setup()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>)
  await screen.findByText('Adaptive LLM Router')
  await user.click(screen.getByRole('button', { name: /higher quality/i }))
  await user.click(screen.getByRole('button', { name: /preview decision/i }))
  expect(await screen.findByText(/Previewed model/)).toBeInTheDocument()
  expect(screen.getByText('nvidia/nemotron:free')).toBeInTheDocument()
})


test('starts a paid benchmark only after the cost estimate is confirmed', async () => {
  const estimate = { pool: 'paid', mode: 'pilot', model_ids: ['google/gemma', 'inception/mercury', 'google/gemini'], samples: 2, cells: 6, worst_case_usd: '0.02268', spend_cap_usd: '1.00', within_cap: true, requires_confirmation: true }
  const runView = { manifest: { run_id: 'gsm8k-paid-pilot-test', mode: 'pilot', status: 'pending', dataset: 'openai/gsm8k', dataset_revision: 'rev', registry_snapshot_id: 'paid', model_ids: estimate.model_ids, generation_config: {}, total_cells: 6, completed_cells: 0, successful_cells: 0, failed_cells: 0, error_message: null }, summary: null }
  const posts: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/benchmarks/runs/latest')) return new Response(JSON.stringify({ detail: 'No benchmark run found' }), { status: 404, headers: { 'Content-Type': 'application/json' } })
    if (url.includes('/benchmarks/gsm8k/runs')) posts.push(String(init?.body))
    const body = url.endsWith('/health')
      ? { ...health, credential_configured: true }
      : url.includes('/routing/dashboard')
        ? dashboard
        : url.includes('/routing/validation')
          ? validation
          : url.includes('/benchmarks/gsm8k/estimate')
            ? estimate
            : url.includes('/benchmarks/gsm8k/runs')
              ? runView
              : { schema_version: '1.0', snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com', models_sha256: 'abc', models: [model('google/gemma', 262144), model('inception/mercury', 1000000), model('google/gemini', 1048576)] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
  const user = userEvent.setup()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>)
  await screen.findByText('Adaptive LLM Router')
  await user.click(screen.getByRole('tab', { name: /benchmark/i }))
  await user.click(await screen.findByRole('button', { name: /run pilot/i }))
  expect(await screen.findByText(/Worst-case cost \$0\.0227 for 6 cells/)).toBeInTheDocument()
  expect(posts).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: /confirm and start/i }))
  await waitFor(() => expect(posts).toHaveLength(1))
  expect(JSON.parse(posts[0])).toEqual({ mode: 'pilot', pool: 'paid', confirmed_estimate_usd: '0.02268' })
})
