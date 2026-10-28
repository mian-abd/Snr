import type {
  BenchmarkEstimate,
  BenchmarkView,
  ComparisonResponse,
  EligibilityResult,
  Health,
  LearnedRouterReport,
  PaginatedRecords,
  RegistrySnapshot,
  RoutingDecision,
  RouteResponse,
  RoutingDashboard,
  RoutingPool,
  RoutingPriority,
  RoutingValidationReport,
} from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Preserve the status-based message when an upstream response is not JSON.
    }
    throw new ApiError(message, response.status)
  }
  return response.json() as Promise<T>
}

export const client = {
  health: () => api<Health>('/api/v1/health'),
  models: (pool: RoutingPool = 'baseline') => api<RegistrySnapshot>(`/api/v1/models?pool=${pool}`),
  routingModels: () => api<RegistrySnapshot>('/api/v1/routing/models'),
  compare: (prompt: string, save: boolean, pool: RoutingPool) =>
    api<ComparisonResponse>('/api/v1/comparisons', {
      method: 'POST',
      body: JSON.stringify({ prompt, save, pool }),
    }),
  route: (prompt: string, priority: RoutingPriority, pool: RoutingPool, minContextTokens: number) =>
    api<RouteResponse>('/api/v1/routes', {
      method: 'POST',
      body: JSON.stringify({ prompt, priority, pool, min_context_tokens: minContextTokens }),
    }),
  previewRoute: (prompt: string, priority: RoutingPriority, pool: RoutingPool, minContextTokens: number) =>
    api<RoutingDecision>('/api/v1/routing/decisions', {
      method: 'POST',
      body: JSON.stringify({ prompt, priority, pool, min_context_tokens: minContextTokens }),
    }),
  routingDashboard: (pool: RoutingPool) => api<RoutingDashboard>(`/api/v1/routing/dashboard?pool=${pool}`),
  routingValidation: (pool: RoutingPool) => api<RoutingValidationReport>(`/api/v1/routing/validation?pool=${pool}`),
  eligibility: (minContextTokens: number) =>
    api<{ results: EligibilityResult[] }>('/api/v1/eligibility', {
      method: 'POST',
      body: JSON.stringify({ min_context_tokens: minContextTokens }),
    }),
  latestBenchmark: async (pool: RoutingPool) => {
    try {
      return await api<BenchmarkView>(`/api/v1/benchmarks/runs/latest?pool=${pool}`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  },
  benchmark: (runId: string) => api<BenchmarkView>(`/api/v1/benchmarks/runs/${runId}`),
  learnedReport: async () => {
    try {
      return await api<LearnedRouterReport>('/api/v1/learned/report')
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  },
  records: (runId: string) =>
    api<PaginatedRecords>(`/api/v1/benchmarks/runs/${runId}/records?limit=100`),
  benchmarkEstimate: (pool: RoutingPool, mode: 'pilot' | 'full') =>
    api<BenchmarkEstimate>(`/api/v1/benchmarks/gsm8k/estimate?pool=${pool}&mode=${mode}`),
  startBenchmark: (mode: 'pilot' | 'full', pool: RoutingPool, confirmedEstimateUsd?: string) =>
    api<BenchmarkView>('/api/v1/benchmarks/gsm8k/runs', {
      method: 'POST',
      body: JSON.stringify({ mode, pool, confirmed_estimate_usd: confirmedEstimateUsd ?? null }),
    }),
}
