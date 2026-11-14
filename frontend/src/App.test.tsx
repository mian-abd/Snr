import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const health = { status: 'ok', version: '0.1.0', registry_loaded: true, registry_snapshot_id: 'snapshot', credential_configured: false, active_benchmark_run_id: null }
const model = (id: string, context: number) => ({ id, display_name: id, provider: id.split('/')[0], context_length: context, pricing: { prompt_per_token: '0', completion_per_token: '0' }, input_modalities: ['text'], output_modalities: ['text'], supported_parameters: [], capabilities: { tools: true, structured_output: true }, enabled: true, snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com' })
const registry = (models: unknown[]) => ({ schema_version: '1.0', snapshot_id: 'snapshot', metadata_as_of: '2026-09-30T00:00:00Z', source_url: 'https://example.com', models_sha256: 'abc', models })
const dashboard = { pool: 'paid', source_run_id: 'saved-run', source_dataset: 'openai/gsm8k', source_cells: 36, model_ids: [], note: 'Offline replay selects from the same saved matrix.', strategies: [], prompts: [] }
const ruleDecision = { strategy_id: 'rule_based_v1', pool: 'baseline', priority: 'quality', min_context_tokens: 1, selected_model_id: 'nvidia/nemotron:free', eligible_model_ids: ['google/gemma:free', 'nvidia/nemotron:free'], task_signals: ['general'], reason: 'Quality priority selects the designated stronger baseline.' }
const validation = { strategy_id: 'rule_based_v1', registry_snapshot_id: 'snapshot', passed: true, passed_cases: 5, total_cases: 5, cases: [] }

const metrics = (logLoss: number) => ({ log_loss: logLoss, brier: 0.15, roc_auc: 0.7, accuracy_at_0_5: 0.8, rows: 6 })
const classifier = (logLoss: number, params: Record<string, number>) => ({ best_params: params, train: metrics(logLoss - 0.1), validation: metrics(logLoss), overfit_gap_log_loss: 0.1, grid: [] })
const task = (correct: number, cost: number) => ({ prompts: 40, correct, accuracy: correct / 40, total_cost_usd: cost, median_latency_ms: 4000 })
const strategy = (id: string, correct: number, cost: number, latency: number, models: Record<string, number>) => ({
  strategy_id: id, prompts: 120, correct, accuracy: correct / 120, total_cost_usd: cost, cost_per_correct_usd: cost / correct, median_latency_ms: latency, p95_latency_ms: latency * 2,
  selected_models: models, by_task: { math: task(38, cost / 3), qa: task(Math.round(correct / 3), cost / 3), code: task(correct - 38 - Math.round(correct / 3), cost / 3) },
})
const weights = (cost: number, latency: number) => ({ quality: 1, cost, latency, reliability: 0 })
const matrixRow = (id: string, name: string, access: string, correct: number, failed = 0) => ({ model_id: id, display_name: name, access, prompts: 600, correct, prompts_by_task: { math: 200, qa: 200, code: 200 }, correct_by_task: { math: 190, qa: Math.max(0, correct - 380), code: Math.min(190, correct) }, failed_calls: failed, median_latency_ms: 5000, cost_usd: 0.5 })
const report = {
  run_id: 'suite', pool_snapshot_id: 'pool-test', models: ['gemini-4-argon', 'gemma-4-26b', 'mercury-3'], models_without_results: ['gemma-4-31b'], features: ['a', 'b'], rows: { train: 12, validation: 4 },
  matrix: [matrixRow('gemini-4-argon', 'Gemini 4 Argon', 'paid', 563), matrixRow('gemma-4-26b', 'Gemma 4 26B', 'paid', 517)],
  classifiers: { logistic_regression: classifier(0.467, { logisticregression__C: 0.01 }), gradient_boosted_trees: classifier(0.491, { max_depth: 2 }) },
  reference_model_task_prior: metrics(0.454),
  selected_family: 'logistic_regression',
  selection_rule: 'Lower validation log loss.',
  validation_prompts: 120,
  strategies: [],
  weight_tuning: [
    { priority: 'quality', weights: weights(0.05, 0.02), validation_correct: 110, validation_cost_usd: 0.44, validation_median_latency_ms: 5000, accuracy_floor: null, candidates_tried: 18 },
    { priority: 'cost', weights: weights(1, 0), validation_correct: 100, validation_cost_usd: 0.004, validation_median_latency_ms: 12000, accuracy_floor: 99, candidates_tried: 42 },
    { priority: 'latency', weights: weights(0.05, 1), validation_correct: 106, validation_cost_usd: 0.1, validation_median_latency_ms: 2000, accuracy_floor: 99, candidates_tried: 42 },
    { priority: 'balanced', weights: weights(0.05, 1), validation_correct: 106, validation_cost_usd: 0.1, validation_median_latency_ms: 2000, accuracy_floor: 99, candidates_tried: 98 },
  ],
  heldout: { artifact_id: 'router-test', trained_on: ['train', 'validation'], prompts: 120, classifier: metrics(0.432), reference_model_task_prior: metrics(0.434), strategies: [], oracle: [], routing_errors: [] },
  note: 'Selected on validation, tested once.',
}
const candidate = (id: string, name: string, score: number | null, reason: string | null = null) => ({
  model_id: id, display_name: name, access: 'paid', provider: 'openrouter', context_length: 262144, data_policy: 'Paid provider policy.', eligible: reason == null, exclusion_reason: reason,
  p_success: 0.9, expected_cost_usd: 0.001, expected_latency_ms: 4000, failure_rate: 0, snapshot_expected_cost_usd: null, catalog_note: null, what_if_note: null,
  score, quality_term: score, cost_penalty: 0, latency_penalty: 0, reliability_penalty: 0,
})
const learnedDecision = {
  strategy_id: 'learned_logistic_v1', artifact_id: 'router-test', pool_snapshot_id: 'pool', priority: 'quality', weights: weights(0.05, 0.02), custom_weights: false,
  task_group: 'math', task_group_inferred: true, task_signals: ['math'], min_context_tokens: 1, selected_model_id: 'gemini-4-argon',
  candidates: [candidate('gemma-4-26b', 'Gemma 4 26B', 0.81), candidate('gemini-4-argon', 'Gemini 4 Argon', 0.93), candidate('qwen-3.5-9b-local', 'Qwen 3.5 9B (local)', null, 'Context 8,192 is below the required 500,000 tokens')],
  reason: 'Highest score under the tuned best-quality preset.', catalog_source: 'live', catalog_checked_at_utc: '2026-11-13T12:00:00Z',
}
const interval = (low: number, high: number) => ({ low, high })
const spread = (id: string) => ({ strategy_id: id, accuracy: interval(0.88, 0.97), total_cost_usd: interval(0.4, 0.5), median_latency_ms: interval(4800, 5600) })
const breakdown = { prompts: 120, correct: 112, wrong: 8, unavoidable: 4, under_routed: 3, over_routed: 108, over_routed_dominated: 70, over_routing_extra_cost_usd: 0.39, total_cost_usd: 0.421, oracle_correct: 116, oracle_cost_usd: 0.0166, regret_correct: 4 }
const comparison = (strategyId: string, baselineId: string, question: string, diff: number, p: number) => ({
  strategy_id: strategyId, baseline_id: baselineId, question, prompts: 120, correct: 112, baseline_correct: 112 - Math.round(diff * 120), only_strategy_correct: 2, only_baseline_correct: 2,
  accuracy_difference: diff, accuracy_difference_ci: interval(diff - 0.02, diff + 0.02), mcnemar_p: p, holm_p: p, cost_difference_usd: -0.072,
  cost_difference_ci: interval(-0.09, -0.05), cost_ratio: 0.855, cost_ratio_ci: interval(0.82, 0.89), median_latency_difference_ms: 200, median_latency_difference_ci: interval(-300, 700),
})
const evaluation = (id: 'cp3_test' | 'final') => ({
  evaluation_id: id, title: id === 'final' ? 'Fresh prompts' : 'Original test split', description: 'Described.', prompts: 120, prompts_by_task: { math: 40, qa: 40, code: 40 },
  models: ['gemini-4-argon', 'gemma-4-26b', 'mercury-3'], catalog_applied: id === 'final', classifier: metrics(0.432), reference_model_task_prior: metrics(0.434),
  matrix: [matrixRow('gemini-4-argon', 'Gemini 4 Argon', 'paid', 563), matrixRow('gemma-4-26b', 'Gemma 4 26B', 'paid', 517), matrixRow('mercury-3', 'Mercury 3', 'paid', 0, 600)],
  strategies: [
    strategy('fixed_cheapest', 103, 0.018, 5100, { 'gemma-4-26b': 120 }),
    strategy('fixed_strongest', 112, 0.493, 5100, { 'gemini-4-argon': 120 }),
    strategy('learned:quality', 112, 0.421, 5300, { 'gemini-4-argon': 80, 'gemma-4-26b': 40 }),
    strategy('learned:cost', 103, 0.0003, 12700, { 'gemma-4-26b': 1, 'gpt-oss-120b': 119 }),
    ...(id === 'final' ? [strategy('learned:latency', 110, 0.2, 2500, { 'gemma-4-26b': 120 }), strategy('learned_no_catalog:latency', 29, 0.1, 400, { 'mercury-3': 86, 'gemini-4-argon': 34 })] : []),
  ],
  oracle: [strategy('oracle:quality', 116, 0.0166, 4200, { 'gemma-4-26b': 60, 'gpt-oss-120b': 60 })],
  uncertainty: ['fixed_cheapest', 'fixed_strongest', 'learned:quality', 'learned:cost'].map(spread),
  comparisons: [
    comparison('learned:quality', 'fixed_strongest', 'Is the best-quality setting as accurate as always using the strongest model, for less?', 0, 1),
    ...(id === 'final' ? [comparison('learned:latency', 'learned_no_catalog:latency', 'How much does the live catalog check protect the fastest setting from the retired model?', 0.67, 0.0001)] : []),
  ],
  routing_errors: [{
    strategy_id: 'learned:quality', overall: breakdown, by_task: { math: { ...breakdown, prompts: 40 }, qa: breakdown, code: breakdown },
    examples: [{ kind: 'good', sample_id: 'gsm8k-test-0042', benchmark: 'gsm8k', task_group: 'math', prompt_excerpt: 'Janet has three apples.', chosen_model_id: 'gemma-4-26b', chosen_correct: true, chosen_cost_usd: 0.0001, chosen_latency_ms: 3000, predicted_success: 0.95, alternative_model_id: 'gemini-4-argon', alternative_correct: true, alternative_cost_usd: 0.004, alternative_latency_ms: 6000, explanation: 'Gemma 4 26B answered right for $0.00010 in 3.0 s.' }],
  }],
})
const scenario = { scenario: { scenario_id: 'observed_drift', title: 'Observed drift (Nov 12-13)', condition: 'availability', observed: true, description: 'Mercury 3 retired.', price_multipliers: {}, latency_multipliers: {}, failure_shares: {}, unavailable: ['mercury-3'], reliability_weight: null, world_already_changed: false }, prompts: 120, strategies: [
  { strategy_id: 'learned:quality', correct: 112, accuracy: 0.93, total_cost_usd: 0.42, median_latency_ms: 5300, changed_decisions: 0, selected_models: {} },
  { strategy_id: 'learned_frozen:quality', correct: 112, accuracy: 0.93, total_cost_usd: 0.42, median_latency_ms: 5300, changed_decisions: 0, selected_models: {} },
  { strategy_id: 'learned:latency', correct: 110, accuracy: 0.92, total_cost_usd: 0.23, median_latency_ms: 5000, changed_decisions: 86, selected_models: {} },
  { strategy_id: 'learned_frozen:latency', correct: 29, accuracy: 0.24, total_cost_usd: 0.1, median_latency_ms: 9900, changed_decisions: 0, selected_models: {} },
  { strategy_id: 'oracle:latency', correct: 116, accuracy: 0.97, total_cost_usd: 0.05, median_latency_ms: 4100, changed_decisions: null, selected_models: {} },
  { strategy_id: 'fixed_strongest', correct: 112, accuracy: 0.93, total_cost_usd: 0.49, median_latency_ms: 5100, changed_decisions: 0, selected_models: {} },
] }
const finalReport = {
  artifact_id: 'router-test', artifact_sha256: 'a'.repeat(64), final_set_sha256: 'b'.repeat(64), pool_snapshot_id: 'pool-test', catalog: null,
  protocol: ['The router was frozen.'], evaluations: [evaluation('cp3_test'), evaluation('final')],
  robustness: ['cp3_test', 'final'].map((id) => ({ evaluation_id: id, prompts: 120, scenarios: [scenario], priority_sweep: [
    { axis: 'cost', weight: 0, correct: 112, accuracy: 0.93, total_cost_usd: 0.49, median_latency_ms: 5100, selected_models: {} },
    { axis: 'cost', weight: 5, correct: 104, accuracy: 0.87, total_cost_usd: 0.0087, median_latency_ms: 9185, selected_models: {} },
  ], notes: ['Replayed.'] })),
  spend_usd: 1.17,
}
const status = (id: string, name: string, available: boolean, note: string, prices: [number, number, number | null, number | null]) => ({
  model_id: id, display_name: name, provider: 'openrouter', upstream_model: id, checked: true, available, note,
  snapshot_prompt_price_per_million: prices[0], snapshot_completion_price_per_million: prices[1], live_prompt_price_per_million: prices[2], live_completion_price_per_million: prices[3], serving_hosts: [], missing_hosts: [],
})
const catalogStatus = {
  source: 'live', pool_snapshot_id: 'pool-test', snapshot_as_of: '2026-10-27T00:00:00Z', checked_at_utc: '2026-11-13T12:00:00Z', error: null,
  models: [
    status('mercury-3', 'Mercury 3', false, 'OpenRouter lists inception/mercury-3 but no host serves it any more (retired)', [0.1, 0.35, null, null]),
    status('gemma-4-26b', 'Gemma 4 26B', true, 'Price changed', [0.0765, 0.255, 0.0675, 0.225]),
  ],
}
const poolModel = (id: string, name: string, prompt: string, completion: string) => ({
  id, display_name: name, family: 'Family', open_weight: true, parameters: '26B', access: 'paid', provider: 'openrouter', base_url: 'https://openrouter.ai/api/v1', upstream_model: id,
  api_key_env: 'OPENROUTER_API_KEY', prompt_price_per_token: prompt, completion_price_per_token: completion, context_length: 262144, requests_per_minute: 60, max_concurrency: 3,
  request_options: { provider: { order: ['nextbit/bf16'] } }, data_policy: 'OpenRouter paid route.', enabled: true,
})
const pool = { schema_version: '1.0', snapshot_id: 'pool-test', metadata_as_of: '2026-10-27T00:00:00Z', models_sha256: 'c'.repeat(64), models: [poolModel('gemma-4-26b', 'Gemma 4 26B', '7.65E-8', '2.55E-7'), poolModel('mercury-3', 'Mercury 3', '1E-7', '3.5E-7')] }
const whatIf = { before: learnedDecision, after: { ...learnedDecision, selected_model_id: 'gemma-4-26b', reason: 'Gemma wins after the change.' }, changed: true }

type Requested = Array<{ url: string; body?: string }>

/** A server with or without a trained router; every response is local. */
function stub(requested: Requested, { trained = true, keyed = false, final = finalReport as unknown } = {}) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    requested.push({ url, body: init?.body ? String(init.body) : undefined })
    if (url.endsWith('/health')) return json({ ...health, credential_configured: keyed })
    if (url.includes('/learned/')) {
      if (!trained) {
        return url.endsWith('/learned/report') || url.endsWith('/learned/final')
          ? json({ detail: 'No report has been generated yet' }, 404)
          : json({ detail: 'The learned router has not been trained yet' }, 503)
      }
      if (url.endsWith('/learned/report')) return json(report)
      if (url.endsWith('/learned/final')) return json(final)
      if (url.includes('/learned/catalog')) return json(catalogStatus)
      if (url.endsWith('/learned/pool')) return json(pool)
      if (url.endsWith('/learned/decisions')) return json(learnedDecision)
      if (url.endsWith('/learned/what-if')) return json(whatIf)
    }
    if (url.includes('/routing/dashboard')) return json(dashboard)
    if (url.includes('/routing/validation')) return json(validation)
    if (url.endsWith('/routing/decisions')) return json(ruleDecision)
    if (url.endsWith('/eligibility')) return json({ results: [] })
    if (url.includes('/benchmarks/runs/latest')) return json({ detail: 'No benchmark run found' }, 404)
    return json(registry([model('google/gemma:free', 262144), model('nvidia/nemotron:free', 1000000)]))
  }))
}

function renderAt(path: string) {
  window.location.hash = path
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>)
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.location.hash = ''
})

test('opens on the home page and explains each page before any training', async () => {
  stub([], { trained: false })
  renderAt('/')
  expect(await screen.findByRole('heading', { name: /good enough/i })).toBeInTheDocument()
  expect(screen.queryByText(/checkpoint/i)).toBeNull()
  await userEvent.setup().click(screen.getAllByRole('link', { name: 'Research' })[0])
  expect(await screen.findByText('No evaluation report yet')).toBeInTheDocument()
})

test('summarizes the findings and the routing flow on the home page', async () => {
  stub([])
  renderAt('/')
  expect(await screen.findByText('What the experiments found')).toBeInTheDocument()
  expect(screen.getByText(/112 of 120 right for \$0\.42, against 112 for \$0\.49/)).toBeInTheDocument()
  expect(screen.getByText('110 vs 29')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: /Models chosen under Best quality: Gemini 4 Argon 67%, Gemma 4 26B 33%/ })).toBeInTheDocument()
  expect(await screen.findByText('1 model unavailable')).toBeInTheDocument()
})

test('previews a decision, names where a run would send the prompt, and stress-tests it', async () => {
  const requested: Requested = []
  stub(requested, { keyed: true })
  renderAt('/router')
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByText(/These are the tuned balanced weights/)).toBeInTheDocument())
  fireEvent.change(screen.getByLabelText(/Speed weight/), { target: { value: '0.6' } })
  expect(screen.getByText(/custom weights/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Preview decision/ }))
  expect(await screen.findByText('Highest score under the tuned best-quality preset.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Gemini 4 Argon' })).toBeInTheDocument()
  expect(screen.getByText(/Run would send this prompt to OpenRouter, a third-party API/)).toBeInTheDocument()
  expect(screen.getByText(/below the required 500,000 tokens/)).toBeInTheDocument()
  const preview = requested.find(({ url }) => url.endsWith('/learned/decisions'))
  expect(JSON.parse(preview!.body!)).toMatchObject({ priority: 'balanced', task_group: null, weights: { quality: 1, latency: 0.6 } })
  await user.click(screen.getByRole('button', { name: 'Simulate' }))
  expect(await screen.findByText('After the change')).toBeInTheDocument()
  expect(screen.getByText('Gemma wins after the change.')).toBeInTheDocument()
  const simulated = requested.find(({ url }) => url.endsWith('/learned/what-if'))
  expect(JSON.parse(simulated!.body!)).toMatchObject({ changes: { latency_multipliers: { 'gemini-4-argon': 3 } } })
  expect(requested.some(({ url }) => url.endsWith('/learned/routes'))).toBe(false)
})

test('lists the models with live availability and prices, and opens one', async () => {
  const requested: Requested = []
  stub(requested)
  renderAt('/models')
  const user = userEvent.setup()
  expect(await screen.findByText('Unavailable')).toBeInTheDocument()
  expect(screen.getByText('$0.0765 / $0.255')).toBeInTheDocument()
  expect(screen.getByText('$0.0675 / $0.225')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Check again/ }))
  await waitFor(() => expect(requested.some(({ url }) => url.endsWith('/learned/catalog/refresh'))).toBe(true))
  await user.click(screen.getByRole('link', { name: /Gemma 4 26B/ }))
  expect(await screen.findByRole('heading', { name: 'Gemma 4 26B', level: 1 })).toBeInTheDocument()
  expect(screen.getByText('Live price, lower than the snapshot')).toBeInTheDocument()
  expect(screen.getByRole('list', { name: 'Share of prompts per priority' })).toBeInTheDocument()
})

test('shows the research: leaderboard, significance, errors, robustness, training, and downloads', async () => {
  const requested: Requested = []
  stub(requested)
  renderAt('/research')
  const user = userEvent.setup()
  expect(await screen.findByRole('heading', { name: 'Does routing pay off?' })).toBeInTheDocument()
  const board = screen.getByRole('table', { name: /Leaderboard · All tasks/ })
  expect(within(board).getByText('Adaptive router · Lowest cost')).toBeInTheDocument()
  expect(within(board).getAllByText('88% – 97%').length).toBeGreaterThan(0)
  await user.click(within(board).getByRole('button', { name: /Show/ }))
  expect(within(board).getByText('Hindsight oracle · Best quality')).toBeInTheDocument()
  expect(screen.getByText('What the live catalog check is worth')).toBeInTheDocument()
  expect(screen.getByText('More accurate')).toBeInTheDocument()
  expect(screen.getByText('Janet has three apples.')).toBeInTheDocument()
  const robustness = screen.getByRole('table', { name: 'Robustness scenarios' })
  expect(within(robustness).getByText('Really happened')).toBeInTheDocument()
  await user.click(screen.getAllByRole('button', { name: 'Fastest' })[0])
  expect(within(robustness).getByText('29/120')).toBeInTheDocument()
  expect(screen.getByRole('table', { name: 'Classifier comparison' })).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: /CSV/ })[0]).toHaveAttribute('href', '/api/v1/learned/export/strategies?format=csv')
  await user.click(screen.getByRole('button', { name: /Original test split/ }))
  expect(screen.getByText(/The held-out fifth of the 600-prompt suite/)).toBeInTheDocument()
  expect(screen.queryByText('What the live catalog check is worth')).toBeNull()
  expect(requested.some(({ url }) => url.includes('/routes') || url.includes('/refresh'))).toBe(false)
})

test('offers only the task filters an evaluation has prompts for', async () => {
  const mathOnly = (item: ReturnType<typeof strategy>) => ({ ...item, by_task: { math: item.by_task.math } })
  stub([], { final: { ...finalReport, evaluations: finalReport.evaluations.map((item) => ({ ...item, strategies: item.strategies.map(mathOnly), oracle: item.oracle.map(mathOnly) })) } })
  renderAt('/research')
  const filter = await screen.findByRole('group', { name: 'Task' })
  expect(within(filter).queryByRole('button', { name: 'Knowledge' })).toBeNull()
  await userEvent.setup().click(within(filter).getByRole('button', { name: 'Math' }))
  expect(screen.getByRole('table', { name: /Leaderboard · Math/ })).toBeInTheDocument()
})

test('answers questions from the data', async () => {
  stub([])
  renderAt('/faq')
  const user = userEvent.setup()
  await user.click(await screen.findByText('How much money does routing save?'))
  expect(await screen.findByText(/answered 112 of 120 fresh prompts correctly for \$0\.42/)).toBeInTheDocument()
  await user.click(screen.getByText('Which model is best for math, knowledge questions, or code?'))
  expect(screen.getAllByText(/Gemini 4 Argon was most accurate/, { selector: 'li' }).length).toBeGreaterThan(0)
})

test('keeps the rule-based router in the lab, with live calls unavailable without a key', async () => {
  stub([])
  renderAt('/lab')
  const user = userEvent.setup()
  expect(await screen.findByRole('button', { name: /route prompt/i })).toBeDisabled()
  expect(screen.getByRole('button', { name: /preview decision/i })).toBeEnabled()
  expect(await screen.findByText(/Offline replay selects from the same saved matrix/i)).toBeInTheDocument()
  expect(await screen.findByText('5/5 passed')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /higher quality/i }))
  await user.click(screen.getByRole('button', { name: /preview decision/i }))
  expect(await screen.findByText(/Previewed model/)).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'nvidia/nemotron:free' })).toBeInTheDocument()
})

test('starts a paid pilot only after the cost estimate is confirmed', async () => {
  const estimate = { pool: 'paid', mode: 'pilot', model_ids: ['google/gemma', 'inception/mercury', 'google/gemini'], samples: 2, cells: 6, worst_case_usd: '0.02268', spend_cap_usd: '1.00', within_cap: true, requires_confirmation: true }
  const runView = { manifest: { run_id: 'pilot-test', mode: 'pilot', status: 'pending', dataset: 'openai/gsm8k', dataset_revision: 'rev', registry_snapshot_id: 'paid', model_ids: estimate.model_ids, generation_config: {}, total_cells: 6, completed_cells: 0, successful_cells: 0, failed_cells: 0, error_message: null }, summary: null }
  const posts: string[] = []
  stub([], { keyed: true })
  const base = globalThis.fetch
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/benchmarks/gsm8k/estimate')) return json(estimate)
    if (url.includes('/benchmarks/gsm8k/runs')) {
      posts.push(String(init?.body))
      return json(runView)
    }
    return base(input, init)
  }))
  renderAt('/lab')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'GSM8K pilot' }))
  await user.click(await screen.findByRole('button', { name: /run pilot/i }))
  expect(await screen.findByText(/Worst-case cost \$0\.0227 for 6 cells/)).toBeInTheDocument()
  expect(posts).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: /confirm and start/i }))
  await waitFor(() => expect(posts).toHaveLength(1))
  expect(JSON.parse(posts[0])).toEqual({ mode: 'pilot', pool: 'paid', confirmed_estimate_usd: '0.02268' })
})

test('switches between light and dark themes', async () => {
  stub([])
  renderAt('/')
  const toggle = await screen.findByRole('button', { name: /Switch to (light|dark) theme/ })
  const before = document.documentElement.dataset.theme
  await userEvent.setup().click(toggle)
  expect(document.documentElement.dataset.theme).not.toBe(before)
})
