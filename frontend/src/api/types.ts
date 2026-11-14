export type Health = {
  status: string
  version: string
  registry_loaded: boolean
  registry_snapshot_id: string | null
  routing_registry_snapshot_id: string | null
  credential_configured: boolean
  active_benchmark_run_id: string | null
}

export type ModelSpec = {
  id: string
  display_name: string
  provider: string
  context_length: number
  pricing: { prompt_per_token: string | null; completion_per_token: string | null }
  input_modalities: string[]
  output_modalities: string[]
  supported_parameters: string[]
  capabilities: { tools: boolean; structured_output: boolean }
  enabled: boolean
  snapshot_id: string
  metadata_as_of: string
  source_url: string
}

export type RegistrySnapshot = {
  schema_version: string
  snapshot_id: string
  metadata_as_of: string
  source_url: string
  models_sha256: string
  models: ModelSpec[]
}

export type GenerationResult = {
  request_id: string
  requested_model_id: string
  served_model_id: string | null
  provider: string
  status: string
  text: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  total_tokens: number | null
  latency_ms: number
  cost_usd: string | null
  cost_source: string
  provider_request_id: string | null
  error_code: string | null
  error_message: string | null
  started_at_utc: string
  completed_at_utc: string
  attempt_number: number
}

export type ComparisonResponse = {
  comparison_id: string
  prompt: string
  pool: RoutingPool
  saved: boolean
  created_at_utc: string
  results: GenerationResult[]
}

export type RoutingPriority = 'cost' | 'quality' | 'latency' | 'balanced'
export type RoutingPool = 'baseline' | 'paid'

export type RoutingDecision = {
  strategy_id: string
  pool: RoutingPool
  priority: RoutingPriority
  min_context_tokens: number
  selected_model_id: string
  eligible_model_ids: string[]
  task_signals: string[]
  reason: string
}

export type RouteResponse = {
  decision: RoutingDecision
  result: GenerationResult
}

export type RoutingStrategySummary = {
  strategy_id: string
  label: string
  selected_model_counts: Record<string, number>
  attempted: number
  successful: number
  failed: number
  correct: number
  accuracy: number
  accuracy_when_served: number | null
  mean_latency_ms: number | null
  median_latency_ms: number | null
  p95_latency_ms: number | null
  total_cost_usd: string | null
  cost_per_correct_usd: string | null
}

export type ReplayCell = {
  model_id: string
  status: string
  correct: boolean
  latency_ms: number
  cost_usd: string | null
}

export type ReplaySelection = {
  strategy_id: string
  model_id: string
  reason: string
}

export type ReplayPrompt = {
  sample_id: string
  source_index: number
  question: string
  task_signals: string[]
  cells: ReplayCell[]
  selections: ReplaySelection[]
}

export type RoutingDashboard = {
  pool: RoutingPool
  source_run_id: string
  source_dataset: string
  source_cells: number
  model_ids: string[]
  note: string
  strategies: RoutingStrategySummary[]
  prompts: ReplayPrompt[]
}

export type RoutingValidationCase = {
  case_id: string
  label: string
  prompt: string
  priority: RoutingPriority
  min_context_tokens: number
  expected_model_id: string
  decision: RoutingDecision
  passed: boolean
}

export type RoutingValidationReport = {
  strategy_id: string
  registry_snapshot_id: string
  passed: boolean
  passed_cases: number
  total_cases: number
  cases: RoutingValidationCase[]
}

export type EligibilityResult = {
  model_id: string
  eligible: boolean
  reasons: string[]
  evaluated_requirements: { min_context_tokens: number; pool: RoutingPool | null }
  model_snapshot_id: string
  pool: RoutingPool | null
}

export type BenchmarkEstimate = {
  pool: RoutingPool
  mode: 'pilot' | 'full'
  model_ids: string[]
  samples: number
  cells: number
  worst_case_usd: string
  spend_cap_usd: string | null
  within_cap: boolean
  requires_confirmation: boolean
}

export type BenchmarkManifest = {
  run_id: string
  mode: 'pilot' | 'full'
  status: string
  dataset: string
  dataset_revision: string
  registry_snapshot_id: string
  model_ids: string[]
  generation_config: Record<string, unknown>
  total_cells: number
  completed_cells: number
  successful_cells: number
  failed_cells: number
  created_at_utc: string
  updated_at_utc: string
  error_message: string | null
}

export type ModelSummary = {
  model_id: string
  attempted: number
  successful: number
  failed: number
  correct: number
  accuracy: number
  mean_latency_ms: number | null
  median_latency_ms: number | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  total_cost_usd: string | null
  error_counts: Record<string, number>
}

export type BenchmarkView = {
  manifest: BenchmarkManifest
  summary: { run_id: string; generated_at_utc: string; models: ModelSummary[] } | null
}

export type BenchmarkRecord = {
  run_id: string
  source_index: number
  sample_id: string
  rendered_prompt: string
  expected_answer: string
  extracted_answer: string | null
  extraction_method: string | null
  exact_match: number
  result: GenerationResult
}

export type PaginatedRecords = {
  items: BenchmarkRecord[]
  total: number
  offset: number
  limit: number
}

export type ClassifierMetrics = {
  log_loss: number
  brier: number
  roc_auc: number | null
  accuracy_at_0_5: number
  rows: number
}

export type ClassifierReport = {
  best_params: Record<string, number>
  train: ClassifierMetrics
  validation: ClassifierMetrics
  overfit_gap_log_loss: number
  grid: Array<{ params: Record<string, number>; train: ClassifierMetrics; validation: ClassifierMetrics }>
}

export type LearnedMatrixRow = {
  model_id: string
  display_name: string
  access: string
  prompts: number
  correct: number
  prompts_by_task: Record<string, number>
  correct_by_task: Record<string, number>
  failed_calls: number
  median_latency_ms: number | null
  cost_usd: number
}

export type LearnedStrategyOutcome = {
  strategy_id: string
  prompts: number
  correct: number
  accuracy: number
  total_cost_usd: number
  cost_per_correct_usd: number | null
  median_latency_ms: number | null
  p95_latency_ms: number | null
  selected_models: Record<string, number>
  by_task: Record<string, StrategyTaskOutcome>
}

export type StrategyTaskOutcome = {
  prompts: number
  correct: number
  accuracy: number
  total_cost_usd: number
  median_latency_ms: number | null
}

export type TaskGroup = 'math' | 'qa' | 'code'

export type RoutingWeights = { quality: number; cost: number; latency: number; reliability: number }

export type WeightTuningResult = {
  priority: RoutingPriority
  weights: RoutingWeights
  validation_correct: number
  validation_cost_usd: number
  validation_median_latency_ms: number | null
  accuracy_floor: number | null
  candidates_tried: number
}

export type RoutingErrorSummary = {
  strategy_id: string
  prompts: number
  wrong: number
  under_routed: number
  over_routed: number
  examples: Array<{ kind: string; sample_id: string; task_group: TaskGroup; chosen_model_id: string; alternative_model_id: string }>
}

export type HeldoutEvaluation = {
  artifact_id: string
  trained_on: string[]
  prompts: number
  classifier: ClassifierMetrics
  reference_model_task_prior: ClassifierMetrics
  strategies: LearnedStrategyOutcome[]
  oracle: LearnedStrategyOutcome[]
  routing_errors: RoutingErrorSummary[]
}

export type LearnedRouterReport = {
  run_id: string
  pool_snapshot_id: string
  models: string[]
  models_without_results: string[]
  features: string[]
  rows: Record<string, number>
  matrix: LearnedMatrixRow[]
  classifiers: Record<string, ClassifierReport>
  reference_model_task_prior: ClassifierMetrics
  selected_family: string
  selection_rule: string
  validation_prompts: number
  strategies: LearnedStrategyOutcome[]
  weight_tuning: WeightTuningResult[]
  heldout: HeldoutEvaluation
  note: string
}

export type LearnedCandidate = {
  model_id: string
  display_name: string
  access: string
  provider: string
  context_length: number
  data_policy: string
  eligible: boolean
  exclusion_reason: string | null
  p_success: number
  expected_cost_usd: number
  expected_latency_ms: number
  failure_rate: number
  snapshot_expected_cost_usd: number | null
  catalog_note: string | null
  what_if_note: string | null
  score: number | null
  quality_term: number | null
  cost_penalty: number | null
  latency_penalty: number | null
  reliability_penalty: number | null
}

export type LearnedRoutingDecision = {
  strategy_id: string
  artifact_id: string
  pool_snapshot_id: string
  priority: RoutingPriority
  weights: RoutingWeights
  custom_weights: boolean
  task_group: TaskGroup
  task_group_inferred: boolean
  task_signals: string[]
  min_context_tokens: number
  selected_model_id: string
  candidates: LearnedCandidate[]
  reason: string
  catalog_source: CatalogSource
  catalog_checked_at_utc: string | null
}

export type LearnedRouteRequest = {
  prompt: string
  priority: RoutingPriority
  weights: RoutingWeights | null
  task_group: TaskGroup | null
  min_context_tokens: number
}

export type LearnedRouteResponse = { decision: LearnedRoutingDecision; result: GenerationResult }

export type CatalogSource = 'live' | 'snapshot' | 'off'

export type LiveModelStatus = {
  model_id: string
  display_name: string
  provider: string
  upstream_model: string
  checked: boolean
  available: boolean
  note: string
  snapshot_prompt_price_per_million: number
  snapshot_completion_price_per_million: number
  live_prompt_price_per_million: number | null
  live_completion_price_per_million: number | null
  serving_hosts: string[]
  missing_hosts: string[]
}

export type LiveCatalogStatus = {
  source: CatalogSource
  pool_snapshot_id: string
  snapshot_as_of: string
  checked_at_utc: string | null
  error: string | null
  models: LiveModelStatus[]
}

export type PoolModel = {
  id: string
  display_name: string
  family: string
  open_weight: boolean
  parameters: string
  access: 'paid' | 'free' | 'local'
  provider: string
  base_url: string
  upstream_model: string
  api_key_env: string | null
  prompt_price_per_token: string
  completion_price_per_token: string
  context_length: number
  requests_per_minute: number
  max_concurrency: number
  request_options: Record<string, unknown>
  data_policy: string
  enabled: boolean
}

export type PoolSnapshot = {
  schema_version: string
  snapshot_id: string
  metadata_as_of: string
  models_sha256: string
  models: PoolModel[]
}

export type WhatIfChanges = {
  price_multipliers: Record<string, number>
  latency_multipliers: Record<string, number>
  failure_shares: Record<string, number>
  unavailable: string[]
}

export type WhatIfResponse = { before: LearnedRoutingDecision; after: LearnedRoutingDecision; changed: boolean }

export type Interval = { low: number; high: number }

export type StrategyUncertainty = {
  strategy_id: string
  accuracy: Interval
  total_cost_usd: Interval
  median_latency_ms: Interval
}

export type PairedComparison = {
  strategy_id: string
  baseline_id: string
  question: string
  prompts: number
  correct: number
  baseline_correct: number
  only_strategy_correct: number
  only_baseline_correct: number
  accuracy_difference: number
  accuracy_difference_ci: Interval
  mcnemar_p: number
  holm_p: number
  cost_difference_usd: number
  cost_difference_ci: Interval
  cost_ratio: number | null
  cost_ratio_ci: Interval | null
  median_latency_difference_ms: number
  median_latency_difference_ci: Interval
}

export type ErrorBreakdown = {
  prompts: number
  correct: number
  wrong: number
  unavoidable: number
  under_routed: number
  over_routed: number
  over_routed_dominated: number
  over_routing_extra_cost_usd: number
  total_cost_usd: number
  oracle_correct: number
  oracle_cost_usd: number
  regret_correct: number
}

export type ErrorExample = {
  kind: 'under' | 'over' | 'good'
  sample_id: string
  benchmark: string
  task_group: TaskGroup
  prompt_excerpt: string
  chosen_model_id: string
  chosen_correct: boolean
  chosen_cost_usd: number
  chosen_latency_ms: number
  predicted_success: number
  alternative_model_id: string | null
  alternative_correct: boolean | null
  alternative_cost_usd: number | null
  alternative_latency_ms: number | null
  explanation: string
}

export type RoutingErrorAnalysis = {
  strategy_id: string
  overall: ErrorBreakdown
  by_task: Record<string, ErrorBreakdown>
  examples: ErrorExample[]
}

export type ScenarioSpec = {
  scenario_id: string
  title: string
  condition: string
  observed: boolean
  description: string
  price_multipliers: Record<string, number>
  latency_multipliers: Record<string, number>
  failure_shares: Record<string, number>
  unavailable: string[]
  reliability_weight: number | null
  world_already_changed: boolean
}

export type ScenarioStrategy = {
  strategy_id: string
  correct: number
  accuracy: number
  total_cost_usd: number
  median_latency_ms: number | null
  changed_decisions: number | null
  selected_models: Record<string, number>
}

export type ScenarioResult = { scenario: ScenarioSpec; prompts: number; strategies: ScenarioStrategy[] }

export type PrioritySweepPoint = {
  axis: 'cost' | 'latency'
  weight: number
  correct: number
  accuracy: number
  total_cost_usd: number
  median_latency_ms: number | null
  selected_models: Record<string, number>
}

export type RobustnessReport = {
  evaluation_id: string
  prompts: number
  scenarios: ScenarioResult[]
  priority_sweep: PrioritySweepPoint[]
  notes: string[]
}

export type EvaluationSet = {
  evaluation_id: 'cp3_test' | 'final'
  title: string
  description: string
  prompts: number
  prompts_by_task: Record<string, number>
  models: string[]
  catalog_applied: boolean
  classifier: ClassifierMetrics
  reference_model_task_prior: ClassifierMetrics
  matrix: LearnedMatrixRow[]
  strategies: LearnedStrategyOutcome[]
  oracle: LearnedStrategyOutcome[]
  uncertainty: StrategyUncertainty[]
  comparisons: PairedComparison[]
  routing_errors: RoutingErrorAnalysis[]
}

export type FinalEvaluationReport = {
  artifact_id: string
  artifact_sha256: string
  final_set_sha256: string
  pool_snapshot_id: string
  catalog: LiveCatalogStatus | null
  protocol: string[]
  evaluations: EvaluationSet[]
  robustness: RobustnessReport[]
  spend_usd: number
}

export type ExportTable = 'strategies' | 'comparisons' | 'errors' | 'robustness' | 'sweep' | 'decisions' | 'cells'
