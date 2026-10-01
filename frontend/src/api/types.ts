export type Health = {
  status: string
  version: string
  registry_loaded: boolean
  registry_snapshot_id: string | null
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
  saved: boolean
  created_at_utc: string
  results: GenerationResult[]
}

export type EligibilityResult = {
  model_id: string
  eligible: boolean
  reasons: string[]
  evaluated_requirements: { min_context_tokens: number }
  model_snapshot_id: string
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
