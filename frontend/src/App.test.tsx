import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

const metrics = (logLoss: number) => ({ log_loss: logLoss, brier: 0.15, roc_auc: 0.7, accuracy_at_0_5: 0.8, rows: 6 })
const classifier = (logLoss: number, params: Record<string, number>) => ({ best_params: params, train: metrics(logLoss - 0.1), validation: metrics(logLoss), overfit_gap_log_loss: 0.1, grid: [] })
const task = (correct: number, cost: number) => ({ prompts: 40, correct, accuracy: correct / 40, total_cost_usd: cost, median_latency_ms: 4000 })
const strategy = (id: string, correct: number, cost: number, latency: number, models: Record<string, number>) => ({
  strategy_id: id, prompts: 120, correct, accuracy: correct / 120, total_cost_usd: cost, cost_per_correct_usd: cost / correct, median_latency_ms: latency, p95_latency_ms: latency * 2,
  selected_models: models, by_task: { math: task(38, cost / 3), qa: task(Math.round(correct / 3), cost / 3), code: task(correct - 38 - Math.round(correct / 3), cost / 3) },
})
const weights = (cost: number, latency: number) => ({ quality: 1, cost, latency, reliability: 0 })
const report = {
  run_id: 'cp3-test', pool_snapshot_id: 'cp3-pool-test', models: ['gemini-4-argon', 'gemma-4-26b'], models_without_results: ['gemma-4-31b'], features: [], rows: { train: 12, validation: 4 },
  matrix: [
    { model_id: 'gemini-4-argon', display_name: 'Gemini 4 Argon', access: 'paid', prompts: 600, correct: 563, prompts_by_task: { math: 200, qa: 200, code: 200 }, correct_by_task: { math: 193, qa: 185, code: 185 }, failed_calls: 1, median_latency_ms: 5400, cost_usd: 2.29 },
    { model_id: 'gemma-4-26b', display_name: 'Gemma 4 26B', access: 'paid', prompts: 600, correct: 517, prompts_by_task: { math: 200, qa: 200, code: 200 }, correct_by_task: { math: 191, qa: 162, code: 164 }, failed_calls: 0, median_latency_ms: 5000, cost_usd: 0.08 },
  ],
  classifiers: { logistic_regression: classifier(0.467, { logisticregression__C: 0.01 }), gradient_boosted_trees: classifier(0.491, { max_depth: 2 }) },
  reference_model_task_prior: metrics(0.454),
  selected_family: 'logistic_regression',
  selection_rule: 'Lower validation log loss.',
  validation_prompts: 120,
  strategies: [strategy('logistic_regression:quality', 110, 0.44, 5000, { 'gemini-4-argon': 120 })],
  weight_tuning: [
    { priority: 'quality', weights: weights(0.05, 0.02), validation_correct: 110, validation_cost_usd: 0.44, validation_median_latency_ms: 5000, accuracy_floor: null, candidates_tried: 18 },
    { priority: 'cost', weights: weights(1, 0), validation_correct: 100, validation_cost_usd: 0.004, validation_median_latency_ms: 12000, accuracy_floor: 99, candidates_tried: 42 },
  ],
  heldout: {
    artifact_id: 'cp3-test-lr', trained_on: ['train', 'validation'], prompts: 120, classifier: metrics(0.432), reference_model_task_prior: metrics(0.434),
    strategies: [
      strategy('fixed_cheapest', 103, 0.018, 5100, { 'gemma-4-26b': 120 }),
      strategy('fixed_strongest', 112, 0.493, 5100, { 'gemini-4-argon': 120 }),
      strategy('learned:quality', 112, 0.421, 5300, { 'gemini-4-argon': 80, 'gemma-4-26b': 40 }),
      strategy('learned:cost', 103, 0.0003, 12700, { 'gemma-4-26b': 1, 'gpt-oss-120b': 119 }),
    ],
    oracle: [strategy('oracle:quality', 116, 0.0166, 4200, { 'gemma-4-26b': 60, 'gpt-oss-120b': 60 })],
    routing_errors: [{ strategy_id: 'learned:quality', prompts: 120, wrong: 8, under_routed: 0, over_routed: 108, examples: [] }],
  },
  note: 'Selected on validation, tested once.',
}
const candidate = (id: string, name: string, score: number | null, reason: string | null = null) => ({
  model_id: id, display_name: name, access: 'paid', provider: 'openrouter', context_length: 262144, data_policy: 'Paid provider policy.', eligible: reason == null, exclusion_reason: reason,
  p_success: 0.9, expected_cost_usd: 0.001, expected_latency_ms: 4000, failure_rate: 0, score, quality_term: score, cost_penalty: 0, latency_penalty: 0, reliability_penalty: 0,
})
const learnedDecision = {
  strategy_id: 'learned_logistic_v1', artifact_id: 'cp3-test-lr', pool_snapshot_id: 'pool', priority: 'quality', weights: weights(0.05, 0.02), custom_weights: false,
  task_group: 'math', task_group_inferred: true, task_signals: ['math'], min_context_tokens: 1, selected_model_id: 'gemini-4-argon',
  candidates: [candidate('gemma-4-26b', 'Gemma 4 26B', 0.81), candidate('gemini-4-argon', 'Gemini 4 Argon', 0.93), candidate('qwen-3.5-9b-local', 'Qwen 3.5 9B (local)', null, 'Context 8,192 is below the required 500,000 tokens')],
  reason: 'Highest score under the tuned higher-quality preset.',
}

function stubLearned(requested: Array<{ url: string; body?: string }>) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    requested.push({ url, body: init?.body ? String(init.body) : undefined })
    const body = url.endsWith('/health')
      ? health
      : url.includes('/routing/dashboard')
        ? dashboard
        : url.includes('/routing/validation')
          ? validation
          : url.endsWith('/learned/report')
            ? report
            : url.endsWith('/learned/decisions')
              ? learnedDecision
              : { schema_version: '1.0', snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com', models_sha256: 'abc', models: [model('google/gemma:free', 262144)] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
}

test('shows the held-out comparison and learned-router results without any provider call', async () => {
  const requested: Array<{ url: string; body?: string }> = []
  stubLearned(requested)
  const user = userEvent.setup()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>)
  await screen.findByText('Adaptive LLM Router')
  await user.click(screen.getByRole('tab', { name: /learned/i }))
  expect(await screen.findByText('563 / 600')).toBeInTheDocument()
  expect(screen.getByText('CHECKPOINT 3')).toBeInTheDocument()
  expect(screen.getByText('cp3-pool-test-cp3')).toBeInTheDocument()
  expect(screen.getByText(/Higher-quality preset: 112 of 120 correct for \$0\.421; always strongest: 112 for \$0\.493/)).toBeInTheDocument()
  expect(screen.getByText('Learned router · lower cost')).toBeInTheDocument()
  expect(screen.getByText('Logistic regression · higher quality')).toBeInTheDocument()
  expect(screen.getByText('C 0.01')).toBeInTheDocument()
  expect(screen.getByText(/predicts as well as either classifier/)).toBeInTheDocument()
  expect(screen.getByText('gemma-4-31b')).toBeInTheDocument()
  expect(screen.getAllByRole('img', { name: /Accuracy against/ })).toHaveLength(2)
  const oracleTable = screen.getByRole('table', { name: 'Oracle gap and routing errors' })
  expect(within(oracleTable).getByText('116 / 120')).toBeInTheDocument()
  expect(within(oracleTable).getByText('108')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'MMLU-Pro' }))
  expect(screen.getByRole('table', { name: 'Held-out comparison · MMLU-Pro' })).toBeInTheDocument()
  expect(requested.some(({ url }) => url.includes('/comparisons') || url.includes('/routes'))).toBe(false)
})

test('previews a learned-router decision with custom weights and no provider call', async () => {
  const requested: Array<{ url: string; body?: string }> = []
  stubLearned(requested)
  const user = userEvent.setup()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>)
  await screen.findByText('Adaptive LLM Router')
  await user.click(screen.getByRole('tab', { name: /learned/i }))
  await screen.findByText('563 / 600')
  fireEvent.change(screen.getByLabelText(/Latency weight/), { target: { value: '0.6' } })
  expect(screen.getByText(/Weights \(custom\)/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /preview decision/i }))
  expect(await screen.findByText('Highest score under the tuned higher-quality preset.')).toBeInTheDocument()
  expect(screen.getByText('SELECTED')).toBeInTheDocument()
  expect(screen.getByText(/below the required 500,000 tokens/)).toBeInTheDocument()
  const preview = requested.find(({ url }) => url.endsWith('/learned/decisions'))
  expect(JSON.parse(preview!.body!)).toMatchObject({ priority: 'balanced', task_group: null, weights: { quality: 1, latency: 0.6 } })
  expect(requested.some(({ url }) => url.endsWith('/learned/routes'))).toBe(false)
})
