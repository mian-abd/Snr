import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

const health = { status: 'ok', version: '0.1.0', registry_loaded: true, registry_snapshot_id: 'snapshot', credential_configured: false, active_benchmark_run_id: null }
const model = (id: string, context: number) => ({ id, display_name: id, provider: id.split('/')[0], context_length: context, pricing: { prompt_per_token: '0', completion_per_token: '0' }, input_modalities: ['text'], output_modalities: ['text'], supported_parameters: [], capabilities: { tools: true, structured_output: true }, enabled: true, snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com' })
const dashboard = { source_run_id: 'checkpoint-1-demo', source_dataset: 'openai/gsm8k', source_cells: 24, note: 'Offline replay from saved evidence.', strategies: [] }
const decision = { strategy_id: 'rule_based_v1', priority: 'quality', min_context_tokens: 1, selected_model_id: 'nvidia/nemotron:free', eligible_model_ids: ['google/gemma:free', 'nvidia/nemotron:free'], task_signals: ['general'], reason: 'Quality priority selects the designated stronger baseline.' }

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('renders checkpoint status and keeps live actions unavailable without a key', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.endsWith('/health')
      ? health
      : url.endsWith('/routing/dashboard')
        ? dashboard
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
})

test('previews a different route priority without a provider credential', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.endsWith('/health')
      ? health
      : url.endsWith('/routing/dashboard')
        ? dashboard
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
  expect(await screen.findByText('Previewed model')).toBeInTheDocument()
  expect(screen.getByText('nvidia/nemotron:free')).toBeInTheDocument()
})
