import type {
  BenchmarkView,
  ComparisonResponse,
  EligibilityResult,
  Health,
  PaginatedRecords,
  RegistrySnapshot,
  RouteResponse,
  RoutingDashboard,
  RoutingPriority,
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
  models: () => api<RegistrySnapshot>('/api/v1/models'),
  compare: (prompt: string, save: boolean) =>
    api<ComparisonResponse>('/api/v1/comparisons', {
      method: 'POST',
      body: JSON.stringify({ prompt, save }),
    }),
  route: (prompt: string, priority: RoutingPriority) =>
    api<RouteResponse>('/api/v1/routes', {
      method: 'POST',
      body: JSON.stringify({ prompt, priority }),
    }),
  routingDashboard: () => api<RoutingDashboard>('/api/v1/routing/dashboard'),
  eligibility: (minContextTokens: number) =>
    api<{ results: EligibilityResult[] }>('/api/v1/eligibility', {
      method: 'POST',
      body: JSON.stringify({ min_context_tokens: minContextTokens }),
    }),
  latestBenchmark: async () => {
    try {
      return await api<BenchmarkView>('/api/v1/benchmarks/runs/latest')
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  },
  benchmark: (runId: string) => api<BenchmarkView>(`/api/v1/benchmarks/runs/${runId}`),
  records: (runId: string) =>
    api<PaginatedRecords>(`/api/v1/benchmarks/runs/${runId}/records?limit=100`),
  startBenchmark: (mode: 'pilot' | 'full') =>
    api<BenchmarkView>('/api/v1/benchmarks/gsm8k/runs', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),
}
