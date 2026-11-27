import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

// jsdom does not scroll; the research page scrolls to the section a link names.
Element.prototype.scrollIntoView ??= () => {}

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
const flagshipEvaluation = (id: 'cp3_test' | 'final') => {
  const base = evaluation(id)
  return {
    ...base,
    models: [...base.models, 'gpt-6.1-sol'],
    matrix: [...base.matrix, matrixRow('gpt-6.1-sol', 'GPT-6.1 Sol', 'paid', 570)],
    strategies: [
      ...base.strategies.filter((item) => item.strategy_id !== 'learned:quality'),
      strategy('learned:quality', 114, 0.3, 4800, { 'gpt-6.1-sol': 60, 'gemma-4-26b': 60 }),
      strategy('previous_router:quality', 112, 0.421, 5300, { 'gemini-4-argon': 80, 'gemma-4-26b': 40 }),
      strategy('fixed_top_added', 115, 0.25, 3000, { 'gpt-6.1-sol': 120 }),
    ],
    comparisons: [comparison('learned:quality', 'previous_router:quality', 'Does the best-quality setting get more right with the flagships in the pool?', 0.017, 0.5)],
  }
}
const flagshipReport = {
  study_id: 'flagship', title: 'With flagship models', question: 'Does adding 1 flagship models to the pool pay off?',
  base_snapshot_id: 'pool-test', added_snapshot_ids: ['flagship-pool-test'], added_from: { 'gpt-6.1-sol': 'flagship' }, cell_tables: ['data/learned/cells.jsonl'],
  added: [poolModel('gpt-6.1-sol', 'GPT-6.1 Sol', '0.000002', '0.00001')],
  excluded: [{ model_id: 'grok-4.7', display_name: 'Grok 4.7', prompts_scored: 372, prompts_total: 900, spend_usd: 2.9, reason: 'Stopped after 372 of 900 prompts.' }],
  strongest_added_id: 'gpt-6.1-sol',
  router: { artifact_id: 'flagship-router-test', family: 'logistic_regression', params: { logisticregression__C: 0.01 }, selection_rule: 'Lower validation log loss.', training_rows: 5000, features: 30,
    classifiers: report.classifiers, reference_model_task_prior: metrics(0.45), validation_prompts: 120, weight_tuning: report.weight_tuning },
  protocol: ['Same recipe.', 'Read once more here.'],
  evaluations: [flagshipEvaluation('cp3_test'), flagshipEvaluation('final')],
  suite_matrix: [matrixRow('gpt-6.1-sol', 'GPT-6.1 Sol', 'paid', 570)],
  spend_usd: { cp3: 0.95, final: 0.5 }, spend_by_model_usd: { 'gpt-6.1-sol': 1.45, 'grok-4.7': 2.9 },
}
const whatIf = { before: learnedDecision, after: { ...learnedDecision, selected_model_id: 'gemma-4-26b', reason: 'Gemma wins after the change.' }, changed: true }
const call = (correct: boolean, latency = 3000, cost = 0.0001, state = 'success') => ({ status: state, correct, latency_ms: latency, cost_usd: cost })
const failed = call(false, 200, 0, 'provider_error')
const explorerModel = (id: string, name: string, added: string | null = null) => ({ model_id: id, display_name: name, access: 'paid', added_from: added })
const picks = (quality: string, cost: string) => ({
  'learned:quality': quality, 'learned:cost': cost, 'learned:latency': cost, 'learned:balanced': quality,
  fixed_cheapest: 'gemma-4-26b', fixed_strongest: 'gemini-4-argon', 'oracle:quality': quality,
})
const explorerPrompt = (id: string, benchmark: string, task: string, question: string, outcomes: Record<string, ReturnType<typeof call>>, choices: Record<string, string>, extra = {}) => ({
  sample_id: id, benchmark, task_group: task, category: null, dataset: 'source/dataset', source_id: id.split('-').pop(), question, options: [], expected_answer: null, answer_note: null, outcomes, choices, ...extra,
})
const explorer = {
  evaluation: 'final',
  models: [explorerModel('gemma-4-26b', 'Gemma 4 26B'), explorerModel('gemini-4-argon', 'Gemini 4 Argon'), explorerModel('mercury-3', 'Mercury 3'), explorerModel('gpt-6.1-sol', 'GPT-6.1 Sol', 'flagship')],
  excluded: [explorerModel('grok-4.7', 'Grok 4.7', 'flagship')],
  strategies: ['fixed_cheapest', 'fixed_strongest', 'learned:balanced', 'learned:cost', 'learned:latency', 'learned:quality', 'oracle:quality'],
  prompts: [
    explorerPrompt('gsm8k-test-0008', 'gsm8k', 'math', 'John drives for 3 hours at 60 mph, then turns around. How far is he from home?',
      { 'gemma-4-26b': call(true), 'gemini-4-argon': call(true, 6000, 0.002), 'mercury-3': failed, 'gpt-6.1-sol': call(true, 2000, 0.001) },
      picks('gemini-4-argon', 'gemma-4-26b'), { expected_answer: '45' }),
    explorerPrompt('mmlu_pro-test-00124', 'mmlu_pro', 'qa', '_______ economy is the term used to describe individuals hired for a specific task.',
      { 'gemma-4-26b': call(false), 'gemini-4-argon': call(false, 9000, 0.0036), 'mercury-3': failed, 'gpt-6.1-sol': call(true, 2000, 0.0011) },
      picks('gemma-4-26b', 'gemma-4-26b'), { category: 'business', options: ['Gig, Flexibility, Risk', 'Sharing, Risk, Autonomy'], expected_answer: 'A' }),
    explorerPrompt('humaneval_plus-001', 'humaneval_plus', 'code', 'def separate_paren_groups(text):\n    """ Split nested parentheses into separate groups. """\n',
      { 'gemma-4-26b': call(false), 'gemini-4-argon': call(true, 7000, 0.003), 'mercury-3': failed, 'gpt-6.1-sol': call(true) },
      picks('gemma-4-26b', 'gemma-4-26b'), { answer_note: 'No single right answer: a solution is right when it passes every HumanEval+ test.' }),
    explorerPrompt('mbpp_plus-017', 'mbpp_plus', 'code', '"""\nWrite a function that returns the perimeter of a square.\n"""\n',
      { 'gemma-4-26b': call(false), 'gemini-4-argon': call(false), 'mercury-3': failed, 'gpt-6.1-sol': call(false) },
      picks('gemini-4-argon', 'gemma-4-26b')),
  ],
}

const fixStrategy = (id: string, correct: number, cost: number, latency: number, models: Record<string, number> = {}) => ({ strategy_id: id, correct, accuracy: correct / 120, total_cost_usd: cost, median_latency_ms: latency, changed_decisions: 0, selected_models: models })
const fixScenario = (id: string, title: string, observed: boolean, unavailable: string[], told: number, old: number) => ({
  scenario: { scenario_id: id, title, condition: 'availability', observed, description: `${title} on 2026-11-26.`, price_multipliers: {}, latency_multipliers: {}, failure_shares: {}, unavailable, reliability_weight: null, world_already_changed: false },
  prompts: 120,
  strategies: ['quality', 'cost', 'latency'].flatMap((priority) => [fixStrategy(`learned:${priority}`, told, 0.2, 5000), fixStrategy(`learned_frozen:${priority}`, old, 0.1, 3000)]),
})
const fixRobustness = (id: string) => ({ evaluation_id: id, prompts: 120, priority_sweep: [], notes: [], scenarios: [
  fixScenario('no_change', 'No change', false, [], 110, 110),
  fixScenario('observed_drift', 'Observed drift (Nov 12-13)', true, ['mercury-3'], 110, 29),
  fixScenario('gemma_mercury_unavailable', 'Gemma 4 26B and Mercury 3 unavailable', true, ['gemma-4-26b', 'mercury-3'], 109, 31),
] })
const fixEvidence = (router: 'frozen' | 'fixed') => ({ evaluation_id: 'final', scenario_id: 'gemma_mercury_unavailable', priority: 'latency', router, told: fixStrategy('learned:latency', 109, 0.2, 5000), old: fixStrategy('learned_frozen:latency', 31, 0.1, 3000), unchanged: fixStrategy('learned:latency', 110, 0.2, 5000), told_vs_old_p: 0.01 })
const fixWeights = { quality: { quality: 1, cost: 0.05, latency: 0.02, reliability: 0.5 }, cost: { quality: 1, cost: 0.5, latency: 0.05, reliability: 0.25 }, latency: { quality: 1, cost: 0.05, latency: 1, reliability: 0.25 }, balanced: { quality: 1, cost: 0.05, latency: 1, reliability: 0.25 } }
const scoringFixReport = {
  study_id: 'scoring-fix', title: 'The scoring fix, tested', artifact_id: 'router-test', artifact_sha256: 'a'.repeat(64), final_set_sha256: 'b'.repeat(64), pool_snapshot_id: 'pool-test',
  reference: { cost_usd: { math: 0.002 }, latency_ms: { math: 13000 } }, frozen_weights: fixWeights, fixed_weights: fixWeights,
  tuning: { classifier: 'router-test', validation_prompts: 120, reliability_floor: 0.25, reliability_grid: [0.25, 0.5], tuning_reference: { cost_usd: {}, latency_ms: {} }, frozen_recipe_reproduced: true, recipe_check_presets: [], reference_only_presets: [], fixed_presets: [], note: 'Tuned on validation.' },
  protocol: ['Offline replay.'], caveats: ['The references live in the report, not the router.'],
  questions: [{ question_id: 'keeps_accuracy', question: 'With no change, does the fixed scoring keep accuracy on the fresh prompts?', rule: 'Yes if no priority is significantly worse.', holds_fresh: true, holds_test: false, answer_fresh: 'Fixed against frozen: cost 264 against 265.', answer_test: 'Test split numbers.', evidence: [fixEvidence('frozen'), fixEvidence('fixed')] }],
  evaluations: ['cp3_test', 'final'].map((id) => ({ evaluation_id: id, title: id === 'final' ? 'Fresh prompts' : 'Original test split', description: 'd', prompts: 120, models: [], matrix: [], comparisons: [], frozen: fixRobustness(id), fixed: fixRobustness(id) })),
  cell_tables: ['data/learned/cells.jsonl'],
}

type Requested = Array<{ url: string; body?: string }>

/** A server with or without a trained router; every response is local. */
function stub(requested: Requested, { trained = true, keyed = false, final = finalReport as unknown, flagships = null as unknown, scoringFix = null as unknown } = {}) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    requested.push({ url, body: init?.body ? String(init.body) : undefined })
    if (url.endsWith('/health')) return json({ ...health, credential_configured: keyed })
    if (url.includes('/learned/')) {
      if (!trained) {
        return url.endsWith('/learned/report') || url.endsWith('/learned/final') || url.includes('/learned/studies') || url.endsWith('/learned/scoring-fix')
          ? json({ detail: 'No report has been generated yet' }, 404)
          : json({ detail: 'The learned router has not been trained yet' }, 503)
      }
      if (url.includes('/learned/prompts')) return json(url.endsWith('evaluation=final') ? explorer : { ...explorer, evaluation: 'cp3_test', prompts: explorer.prompts.slice(0, 1) })
      if (url.endsWith('/learned/report')) return json(report)
      if (url.endsWith('/learned/final')) return json(final)
      if (url.endsWith('/learned/scoring-fix')) return scoringFix ? json(scoringFix) : json({ detail: 'The scoring-fix study has not been run yet' }, 404)
      if (url.endsWith('/learned/studies')) return json(flagships ? [{ study_id: 'flagship', title: 'With flagship models', question: 'Q', added: 1, pool: 'flagships' }] : [])
      if (url.endsWith('/learned/studies/flagship') && flagships) return json(flagships)
      if (url.includes('/learned/studies/')) return json({ detail: 'No study has been run' }, 404)
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
  expect(await screen.findByText(/112 of 120 right for \$0\.42, against 112 for \$0\.49/)).toBeInTheDocument()
  expect(screen.getByRole('img', { name: /^Right answers on fresh prompts: Gemini 4 Argon/ })).toBeInTheDocument()
  expect(screen.getByRole('listitem', { name: /Best quality: Gemini 4 Argon 67%, Gemma 4 26B 33%/ })).toBeInTheDocument()
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
  expect(screen.getByText('$0.0675')).toBeInTheDocument()
  expect(screen.getByText('$0.225')).toBeInTheDocument()
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

test('adds the scoring fix to the research, its sections and the search, once the study exists', async () => {
  stub([], { scoringFix: scoringFixReport })
  renderAt('/research')
  expect(await screen.findByRole('heading', { name: 'Fixing the scoring flaw' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Fixing the scoring flaw' })).toBeInTheDocument()
  const questions = screen.getByRole('table', { name: 'The fixed questions and their answers' })
  expect(within(questions).getByText('Fixed against frozen: cost 264 against 265.')).toBeInTheDocument()
  expect(within(questions).getAllByText('Yes').length).toBe(1)
  const drift = screen.getByRole('table', { name: /Mercury 3 retired next to Gemma 4 26B and Mercury 3 unavailable/ })
  expect(within(drift).getAllByText('109/120').length).toBeGreaterThan(0)
  expect(within(drift).getAllByText('31/120').length).toBeGreaterThan(0)
  expect(screen.getByText('Scoring fix: scenarios')).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: /CSV/ }).map((link) => link.getAttribute('href'))).toContain('/api/v1/learned/export/scoring_fix?format=csv')
  cleanup()
  stub([])
  renderAt('/research')
  expect(await screen.findByRole('heading', { name: 'Does routing pay off?' })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Fixing the scoring flaw' })).toBeNull()
})

test('adds the flagship study to the research, the catalog, and the router', async () => {
  const requested: Requested = []
  stub(requested, { flagships: flagshipReport })
  renderAt('/research')
  const user = userEvent.setup()
  expect(await screen.findByRole('heading', { name: 'With flagship models' })).toBeInTheDocument()
  expect(screen.getByText('Grok 4.7 is not in this comparison.')).toBeInTheDocument()
  const table = screen.getByRole('table', { name: 'With flagship models: strategies' })
  expect(within(table).getByText('Always GPT-6.1 Sol')).toBeInTheDocument()
  expect(within(table).getByText('Frozen router · Best quality')).toBeInTheDocument()
  expect(screen.getByText('Does the best-quality setting get more right with the flagships in the pool?')).toBeInTheDocument()
  cleanup()
  renderAt('/models')
  expect(await screen.findByText(/OpenAI · Paid · Flagship/)).toBeInTheDocument()
  cleanup()
  renderAt('/router')
  await user.click(await screen.findByRole('button', { name: /With flagships/ }))
  await waitFor(() => expect(requested.some(({ url, body }) => url.endsWith('/learned/decisions') && body?.includes('"pool":"flagships"'))).toBe(true))
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

test('opens the search palette with Ctrl K, closes it with Escape, and goes to a model', async () => {
  stub([])
  renderAt('/')
  const user = userEvent.setup()
  await screen.findByRole('heading', { name: /good enough/i })
  const trigger = screen.getByRole('button', { name: 'Search' })
  trigger.focus()
  await user.keyboard('{Control>}k{/Control}')
  const dialog = await screen.findByRole('dialog', { name: 'Search the site' })
  expect(within(dialog).getByRole('combobox')).toHaveFocus()
  expect(within(dialog).getByRole('option', { name: /^Compare/ })).toBeInTheDocument()
  expect(within(dialog).getByRole('option', { name: /^Method and limits/ })).toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(trigger).toHaveFocus()

  await user.keyboard('{Control>}k{/Control}')
  await user.keyboard('gema 26')
  await waitFor(() => expect(screen.getAllByRole('option')[0]).toHaveTextContent(/Gemma 4 26B/))
  expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByText(/86\.2%/)).toBeInTheDocument()
  await user.keyboard('{Enter}')
  expect(await screen.findByRole('heading', { name: 'Gemma 4 26B', level: 1 })).toBeInTheDocument()
  expect(window.location.hash).toBe('#/models/gemma-4-26b')
  expect(screen.queryByRole('dialog')).toBeNull()
})

test('moves through the search results with the arrow keys and opens a research section', async () => {
  stub([])
  renderAt('/models')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Search' }))
  await user.keyboard('limits')
  const options = await screen.findAllByRole('option')
  expect(options[0]).toHaveTextContent('Method and limits')
  await user.keyboard('{ArrowDown}{ArrowUp}')
  expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true')
  await user.keyboard('{Enter}')
  await waitFor(() => expect(window.location.hash).toBe('#/research?section=method'))
})

test('compares two models from the address, side by side', async () => {
  stub([], { flagships: flagshipReport })
  renderAt('/compare?models=gemma-4-26b,gpt-6.1-sol')
  const user = userEvent.setup()
  const table = await screen.findByRole('table', { name: 'Model comparison' })
  expect(within(table).getByRole('columnheader', { name: /Gemma 4 26B/ })).toBeInTheDocument()
  expect(within(table).getByRole('columnheader', { name: /GPT-6.1 Sol/ })).toBeInTheDocument()
  const overall = within(table).getAllByRole('row').find((row) => within(row).queryByRole('rowheader', { name: 'All tasks' }))!
  expect(within(overall).getByText('86.2%')).toBeInTheDocument()
  expect(within(overall).getByText('Best').closest('td')).toHaveTextContent('95.0%')
  expect(within(table).getAllByText('Not in its pool').length).toBeGreaterThan(0)
  expect(within(table).getByText('Router + flagships')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: /^Accuracy by task/ })).toBeInTheDocument()
  await user.click(within(table).getByRole('button', { name: 'Remove GPT-6.1 Sol from the comparison' }))
  await waitFor(() => expect(window.location.hash).toBe('#/compare?models=gemma-4-26b'))
  expect(within(screen.getByRole('table', { name: 'Model comparison' })).queryByRole('columnheader', { name: /GPT-6.1 Sol/ })).toBeNull()
})

test('offers quick picks on an empty comparison and adds a model with the picker', async () => {
  stub([], { flagships: flagshipReport })
  renderAt('/compare')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /The two most accurate/ }))
  await waitFor(() => expect(window.location.hash).toBe('#/compare?models=gpt-6.1-sol,gemma-4-26b'))
  expect(await screen.findByRole('table', { name: 'Model comparison' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Add a model/ }))
  await user.keyboard('merc{Enter}')
  await waitFor(() => expect(window.location.hash).toBe('#/compare?models=gpt-6.1-sol,gemma-4-26b,mercury-3'))
  expect(await screen.findByRole('columnheader', { name: /Mercury 3/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Add a model/ })).toHaveFocus()
})

test('picks models in the table and opens them on the compare page', async () => {
  stub([])
  renderAt('/models')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('checkbox', { name: 'Pick Gemma 4 26B to compare' }))
  await user.click(screen.getByRole('checkbox', { name: 'Pick Mercury 3 to compare' }))
  const bar = screen.getByRole('region', { name: 'Models picked to compare' })
  expect(within(bar).getByText('2 of 4 picked')).toBeInTheDocument()
  await user.click(within(bar).getByRole('button', { name: 'Compare 2 models' }))
  await waitFor(() => expect(window.location.hash).toBe('#/compare?models=gemma-4-26b,mercury-3'))
  expect(await screen.findByRole('table', { name: 'Model comparison' })).toBeInTheDocument()
})

test('filters the models by maker and downloads the rows shown as CSV', async () => {
  stub([])
  renderAt('/models')
  const user = userEvent.setup()
  const makers = await screen.findByRole('group', { name: 'Filter by maker' })
  await user.click(within(makers).getByRole('button', { name: 'Inception' }))
  expect(within(makers).getByRole('button', { name: 'Inception' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByRole('link', { name: /Gemma 4 26B/ })).toBeNull()
  expect(screen.getByRole('link', { name: /Mercury 3/ })).toBeInTheDocument()
  let saved: Blob | undefined
  URL.createObjectURL = vi.fn((blob: Blob) => { saved = blob; return 'blob:models' })
  URL.revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  await user.click(screen.getByRole('button', { name: /Download CSV/ }))
  expect(click).toHaveBeenCalledOnce()
  const text = await new Promise<string>((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.readAsText(saved!)
  })
  // trim() also drops the byte-order mark that tells spreadsheets the file is UTF-8.
  const lines = text.trim().split('\r\n')
  expect(lines).toHaveLength(2)
  expect(lines[0]).toMatch(/^Model,Maker,Access,Added in study,"Accuracy, all tasks/)
  expect(lines[1]).toBe('Mercury 3,Inception,Paid,,,,,,0.1,0.35,,,262144,Unavailable')
})

test('switches between light and dark themes', async () => {
  stub([])
  renderAt('/')
  const toggle = await screen.findByRole('button', { name: /Switch to (light|dark) theme/ })
  const before = document.documentElement.dataset.theme
  await userEvent.setup().click(toggle)
  expect(document.documentElement.dataset.theme).not.toBe(before)
})

test('draws the robustness scenarios as dumbbells that follow the priority and the measure', async () => {
  stub([])
  renderAt('/research')
  const user = userEvent.setup()
  const chart = await screen.findByRole('list', { name: /^Robustness, right answers, Best quality setting/ })
  const drift = within(chart).getByRole('listitem', { name: /^Observed drift \(Nov 12-13\), really happened\. Told about the change: 112 of 120 right/ })
  expect(within(drift).getByText('Really happened')).toBeInTheDocument()
  expect(within(drift).getByText('Same')).toBeInTheDocument()
  const section = screen.getByRole('region', { name: 'When prices, speed, or providers change' })
  await user.click(within(section).getByRole('button', { name: 'Fastest' }))
  const fastest = screen.getByRole('list', { name: /^Robustness, right answers, Fastest setting/ })
  expect(within(fastest).getByRole('listitem', { name: /Old estimates: 29 of 120 right.*86 choices changed when told/ })).toBeInTheDocument()
  expect(within(fastest).getByText('+81 right')).toBeInTheDocument()
  fireEvent.focus(within(fastest).getAllByRole('listitem')[0])
  expect(within(fastest).getByText('Choices changed: 86 told, 0 with old estimates')).toBeInTheDocument()
  await user.click(within(section).getByRole('button', { name: 'Billed cost' }))
  const cost = screen.getByRole('list', { name: /^Robustness, billed cost, Fastest setting/ })
  expect(within(cost).getByText('+$0.13')).toBeInTheDocument()
  // The table is still there, folded under the chart.
  expect(within(screen.getByRole('table', { name: 'Robustness scenarios' })).getByText('29/120')).toBeInTheDocument()
})

test('picks a weight in the priority sweep and shows where its prompts went', async () => {
  const point = (axis: string, weight: number, correct: number, cost: number, latency: number, models: Record<string, number>) => ({
    axis, weight, correct, accuracy: correct / 120, total_cost_usd: cost, median_latency_ms: latency, selected_models: models,
  })
  const sweep = [
    point('cost', 0, 112, 0.49, 5100, { 'gemini-4-argon': 120 }),
    point('cost', 1, 108, 0.05, 6000, { 'gemma-4-26b': 80, 'gemini-4-argon': 40 }),
    point('cost', 5, 104, 0.0087, 9185, { 'gemma-4-26b': 120 }),
    point('latency', 0, 112, 0.49, 5100, { 'gemini-4-argon': 120 }),
    point('latency', 2, 100, 0.1, 2000, { 'mercury-3': 90, 'gemini-4-argon': 30 }),
  ]
  stub([], { final: { ...finalReport, robustness: finalReport.robustness.map((item) => ({ ...item, priority_sweep: sweep })) } })
  renderAt('/research')
  const user = userEvent.setup()
  // It opens on the weight where most of the saving has arrived.
  const slider = await screen.findByRole('slider', { name: 'Cost weight' })
  expect(slider).toHaveAttribute('aria-valuetext', '1')
  expect(screen.getByRole('listitem', { name: 'Cost weight 1: Gemma 4 26B 67%, Gemini 4 Argon 33%' })).toBeInTheDocument()
  expect(screen.getByText(/4 fewer than at weight 0/)).toBeInTheDocument()
  fireEvent.change(slider, { target: { value: '2' } })
  expect(screen.getByRole('listitem', { name: 'Cost weight 5: Gemma 4 26B 100%' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /^Cost weight 5, 104 of 120 right/, pressed: true })).toBeInTheDocument()
  // A mark picks its weight from the keyboard too.
  fireEvent.keyDown(screen.getByRole('button', { name: /^Cost weight 0, 112 of 120 right/ }), { key: 'Enter' })
  expect(screen.getByRole('listitem', { name: 'Cost weight 0: Gemini 4 Argon 100%' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Speed weight' }))
  expect(screen.getByRole('slider', { name: 'Speed weight' })).toHaveAttribute('aria-valuetext', '2')
  expect(screen.getByRole('listitem', { name: 'Speed weight 2: Mercury 3 75%, Gemini 4 Argon 25%' })).toBeInTheDocument()
  expect(screen.getByRole('table', { name: 'Priority sweep: speed weight' })).toBeInTheDocument()
})

test('finds the prompt explorer from search, filters the prompts, and opens one', async () => {
  stub([])
  renderAt('/')
  const user = userEvent.setup()
  await screen.findByRole('heading', { name: /good enough/i })
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await user.keyboard('prompts')
  await waitFor(() => expect(screen.getAllByRole('option')[0]).toHaveTextContent(/^Prompts/))
  await user.keyboard('{Enter}')
  expect(await screen.findByRole('heading', { name: 'Every prompt, every answer' })).toBeInTheDocument()
  expect(window.location.hash).toBe('#/prompts')
  const rowsOf = () => within(screen.getByRole('list', { name: 'Prompts' })).getAllByRole('listitem')
  await screen.findByRole('list', { name: 'Prompts' })
  expect(rowsOf()).toHaveLength(4)
  expect(screen.getByText(/^Showing/)).toHaveTextContent('Showing 1–4 of 4 prompts. The router (best quality) got 1 of them right.')

  // Each row: a strip with a text alternative, and the router's pick for the chosen priority.
  const first = rowsOf()[0]
  expect(within(first).getByRole('img', { name: 'How each model did: 3 of 4 right. Right: Gemma 4 26B, Gemini 4 Argon, GPT-6.1 Sol. Failed call: Mercury 3.' })).toBeInTheDocument()
  expect(within(first).getByText('Gemini 4 Argon')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Lowest cost' }))
  expect(within(rowsOf()[0]).getByText('Gemma 4 26B')).toBeInTheDocument()
  // From the keyboard, the arrow keys name one model at a time.
  const strip = within(rowsOf()[0]).getByRole('img')
  fireEvent.focus(strip)
  fireEvent.keyDown(strip, { key: 'ArrowRight' })
  expect(within(strip).getByText('Arrow keys for the other models')).toBeInTheDocument()
  expect(within(strip).getByText('Gemini 4 Argon')).toBeInTheDocument()
  fireEvent.blur(strip)
  await user.click(screen.getByRole('button', { name: 'Best quality' }))

  const quick = screen.getByRole('group', { name: 'Show' })
  expect(within(quick).getByRole('button', { name: 'No model right 1' })).toBeInTheDocument()
  expect(within(quick).getByRole('button', { name: 'Only one model right 1' })).toBeInTheDocument()
  await user.click(within(quick).getByRole('button', { name: 'Router wrong 3' }))
  expect(within(quick).getByRole('button', { name: 'Router wrong 3' })).toHaveAttribute('aria-pressed', 'true')
  expect(rowsOf()).toHaveLength(3)
  expect(window.location.hash).toBe('#/prompts?show=router-wrong')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Task' }), 'code')
  expect(rowsOf()).toHaveLength(2)
  // Only a model the router could have chosen makes a miss avoidable.
  expect(within(quick).getByRole('button', { name: 'Router wrong, another model right 1' })).toBeInTheDocument()
  await user.type(screen.getByRole('searchbox', { name: 'Search' }), 'parentheses')
  expect(rowsOf()).toHaveLength(1)
  expect(rowsOf()[0]).toHaveTextContent('Split nested parentheses into separate groups.')
  expect(window.location.hash).toBe('#/prompts?task=code&show=router-wrong&q=parentheses')

  await user.click(within(rowsOf()[0]).getByRole('link'))
  expect(await screen.findByRole('heading', { name: 'Code prompt from HumanEval+', level: 1 })).toBeInTheDocument()
  expect(window.location.hash).toBe('#/prompts/humaneval_plus-001?task=code&show=router-wrong&q=parentheses')
  expect(screen.getByText(/passes every HumanEval\+ test/)).toBeInTheDocument()
  expect(screen.getByText('1 of 1')).toBeInTheDocument()
  const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' })
  expect(within(crumbs).getByRole('link', { name: 'Prompts' })).toHaveAttribute('href', '#/prompts?task=code&show=router-wrong&q=parentheses')
})

test('shows one prompt: the expected answer, every model, and which strategies chose each', async () => {
  stub([])
  renderAt('/prompts/mmlu_pro-test-00124')
  const user = userEvent.setup()
  expect(await screen.findByRole('heading', { name: 'Knowledge prompt from MMLU-Pro', level: 1 })).toBeInTheDocument()
  expect(within(screen.getByRole('list', { name: 'Options' })).getAllByRole('listitem')[0]).toHaveTextContent('Expected')
  expect(screen.getByText('2 of 4')).toBeInTheDocument()

  const router = screen.getByRole('region', { name: 'Where the router sent it' })
  expect(within(router).getAllByText('Gemma 4 26B')).toHaveLength(4)
  expect(within(router).getAllByText('Wrong')).toHaveLength(4)

  const table = screen.getByRole('table', { name: 'Every model on this prompt' })
  const rows = within(table).getAllByRole('row').slice(1)
  expect(rows[0]).toHaveTextContent(/GPT-6\.1 Sol.*Flagship.*Right/)
  const gemma = rows.find((row) => within(row).queryByRole('link', { name: /Gemma 4 26B/ }))!
  expect(within(gemma).getByText('Wrong')).toBeInTheDocument()
  expect(within(gemma).getByText('Router · Best quality')).toBeInTheDocument()
  expect(within(gemma).getByText('Always cheapest')).toHaveAttribute('title', 'Always the cheapest paid model')
  expect(within(gemma).getByRole('link', { name: /Gemma 4 26B/ })).toHaveAttribute('href', '#/models/gemma-4-26b')
  const mercury = rows.find((row) => within(row).queryByRole('link', { name: /Mercury 3/ }))!
  expect(within(mercury).getByText('Failed call')).toBeInTheDocument()
  expect(within(mercury).getByText('Provider error')).toBeInTheDocument()
  expect(screen.getAllByText(/Grok 4\.7 answered only some of these prompts/).length).toBeGreaterThan(0)

  await user.click(screen.getByRole('link', { name: 'Next' }))
  expect(await screen.findByRole('heading', { name: 'Code prompt from HumanEval+', level: 1 })).toBeInTheDocument()
  expect(window.location.hash).toBe('#/prompts/humaneval_plus-001')
  cleanup()
  renderAt('/prompts/no-such-prompt')
  expect(await screen.findByText('Prompt not found')).toBeInTheDocument()
})

test('shows each candidate score as a bar with its penalties cut off', async () => {
  stub([], { keyed: true })
  const base = globalThis.fetch
  const scored = (id: string, name: string, p: number, cost: number, time: number) => ({
    ...candidate(id, name, p - cost - time), p_success: p, quality_term: p, cost_penalty: cost, latency_penalty: time,
  })
  const decision = { ...learnedDecision, candidates: [
    scored('gemini-4-argon', 'Gemini 4 Argon', 0.95, 0.05, 0.2),
    scored('gemma-4-26b', 'Gemma 4 26B', 0.9, 0.004, 0.1),
    candidate('qwen-3.5-9b-local', 'Qwen 3.5 9B (local)', null, 'Context 8,192 is below the required 500,000 tokens'),
  ], selected_model_id: 'gemma-4-26b' }
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => (String(input).endsWith('/learned/decisions') ? json(decision) : base(input, init))))
  renderAt('/router')
  expect(await screen.findByText('How every model scored')).toBeInTheDocument()
  const gemma = await screen.findByRole('img', { name: 'Gemma 4 26B: chance right 0.900, minus cost 0.004, time 0.100, and failures 0.000, scores 0.80' })
  expect(screen.getByRole('img', { name: /^Gemini 4 Argon: chance right 0\.950, minus cost 0\.050, time 0\.200.*scores 0\.70$/ })).toBeInTheDocument()
  expect(screen.getByText('Picked')).toBeInTheDocument()
  expect(screen.getByText('Not considered: Context 8,192 is below the required 500,000 tokens')).toBeInTheDocument()
  expect(screen.getByText('Time penalty')).toBeInTheDocument()
  fireEvent.focus(gemma)
  expect(screen.getByText('= Score')).toBeInTheDocument()
})
