import { useQuery } from '@tanstack/react-query'
import { client } from '../api/client'
import type {
  EvaluationSet,
  FinalEvaluationReport,
  LearnedMatrixRow,
  LearnedRouterReport,
  LearnedStrategyOutcome,
  LiveCatalogStatus,
  LiveModelStatus,
  PoolModel,
  PoolSnapshot,
  RoutingPriority,
} from '../api/types'

export const catalogKey = ['learned-catalog']

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: client.health, refetchInterval: 15_000 })
export const useFinalReport = () => useQuery({ queryKey: ['final-report'], queryFn: client.finalReport, staleTime: Infinity })
export const useLearnedReport = () => useQuery({ queryKey: ['learned-report'], queryFn: client.learnedReport, staleTime: Infinity })
export const usePool = () => useQuery({ queryKey: ['learned-pool'], queryFn: client.learnedPool, staleTime: Infinity })
export const useCatalog = () => useQuery({ queryKey: catalogKey, queryFn: client.learnedCatalog })

export const priorityOrder: RoutingPriority[] = ['quality', 'cost', 'latency', 'balanced']
export const priorityLabel: Record<RoutingPriority, string> = {
  quality: 'Best quality',
  cost: 'Lowest cost',
  latency: 'Fastest',
  balanced: 'Balanced',
}
export const priorityHint: Record<RoutingPriority, string> = {
  quality: 'As many right answers as possible',
  cost: 'Cheapest, but at least as accurate as the cheapest paid model',
  latency: 'Quickest, but at least as accurate as the cheapest paid model',
  balanced: 'Accuracy, cost, and speed together',
}

const fixedLabels: Record<string, string> = {
  fixed_cheapest: 'Always the cheapest paid model',
  fixed_strongest: 'Always the strongest model',
  rule_balanced: 'Rule-based router',
  rule_balanced_no_catalog: 'Rule-based router, no live check',
}
const familyLabels: Record<string, string> = {
  learned: 'Adaptive router',
  learned_no_catalog: 'Adaptive router, no live check',
  learned_frozen: 'Adaptive router, old estimates',
  model_task_prior: 'Per-task averages only',
  oracle: 'Hindsight oracle',
}

export function strategyFamily(id: string) {
  if (fixedLabels[id]) return id.startsWith('rule') ? 'rule' : 'fixed'
  return id.split(':')[0]
}

export function strategyLabel(id: string) {
  if (fixedLabels[id]) return fixedLabels[id]
  const [family, priority] = id.split(':')
  const name = familyLabels[family] ?? family
  return priority ? `${name} · ${priorityLabel[priority as RoutingPriority] ?? priority}` : name
}

export const evaluationLabel: Record<EvaluationSet['evaluation_id'], { title: string; short: string; about: string }> = {
  final: {
    title: 'Fresh prompts',
    short: 'Fresh',
    about: 'Prompts no model or router had seen, drawn after the router was frozen and answered after two real provider changes.',
  },
  cp3_test: {
    title: 'Original test split',
    short: 'Original',
    about: 'The held-out fifth of the 600-prompt suite the router was built on, answered before the provider changes.',
  },
}

export type ModelView = {
  id: string
  pool: PoolModel
  status: LiveModelStatus | undefined
  inRouter: boolean
  fresh: LearnedMatrixRow | undefined
  suite: LearnedMatrixRow | undefined
}

export function modelViews(
  pool: PoolSnapshot | null | undefined,
  catalog: LiveCatalogStatus | null | undefined,
  learned: LearnedRouterReport | null | undefined,
  final: FinalEvaluationReport | null | undefined,
): ModelView[] {
  if (!pool) return []
  const status = new Map(catalog?.models.map((item) => [item.model_id, item]))
  const fresh = new Map(final?.evaluations.find((item) => item.evaluation_id === 'final')?.matrix.map((row) => [row.model_id, row]))
  const suite = new Map(learned?.matrix.map((row) => [row.model_id, row]))
  const routed = new Set(learned?.models ?? [])
  return pool.models.map((model) => ({
    id: model.id,
    pool: model,
    status: status.get(model.id),
    inRouter: routed.size === 0 || routed.has(model.id),
    fresh: fresh.get(model.id),
    suite: suite.get(model.id),
  }))
}

/** Provider families get a stable tint so avatars are recognizable at a glance. */
const tints: Array<[RegExp, string]> = [
  [/gemini/i, '#3b6fd8'],
  [/gemma/i, '#1f8a9e'],
  [/deepseek/i, '#4c62e8'],
  [/nemotron|nvidia/i, '#4f9a1d'],
  [/gpt-oss|openai/i, '#3a3a3a'],
  [/llama|meta/i, '#1d6fe0'],
  [/local/i, '#2f7d4f'],
  [/qwen|alibaba/i, '#7a4fd8'],
  [/mercury|inception/i, '#c0582f'],
]

/** Short, distinct codes for the pool's models; anything else gets its initials. */
const codes: Record<string, string> = {
  'gemma-4-26b': 'Gm', 'gemma-4-31b': 'Gm', 'gemini-4-argon': 'Gi', 'deepseek-v4-flash': 'Ds',
  'deepseek-v4.1-flash': 'Ds', 'nemotron-3-ultra-free': 'Nv', 'gpt-oss-120b': 'Oa', 'llama-3.3-70b': 'Ll',
  'qwen-3.8-27b': 'Qw', 'qwen-3.5-9b-local': 'Qw', 'mercury-3': 'Me',
}

export function avatarFor(model: { id: string; display_name: string }) {
  const tint = tints.find(([pattern]) => pattern.test(model.id))?.[1] ?? '#6b6b6b'
  const words = model.display_name.replace(/\(.*?\)/g, '').trim().split(/\s+/)
  const letters = codes[model.id] ?? `${words[0][0] ?? '?'}${(words[1]?.[0] ?? '').toLowerCase()}`
  return { tint, letters }
}

export const accessLabel: Record<string, string> = { paid: 'Paid', free: 'Free', local: 'On this computer' }
export const providerLabel: Record<string, string> = {
  openrouter: 'OpenRouter',
  ovhcloud: 'OVHcloud AI Endpoints',
  ollama: 'Ollama (local)',
  google_ai_studio: 'Google AI Studio',
  nvidia_nim: 'NVIDIA NIM',
}

export function find(strategies: LearnedStrategyOutcome[], id: string) {
  return strategies.find((item) => item.strategy_id === id)
}

export function evaluationOf(report: FinalEvaluationReport | null | undefined, id: EvaluationSet['evaluation_id']) {
  return report?.evaluations.find((item) => item.evaluation_id === id)
}
