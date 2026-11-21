import { useQuery } from '@tanstack/react-query'
import { client } from '../api/client'
import type {
  EvaluationSet,
  ExplorerEvaluation,
  FinalEvaluationReport,
  PoolStudyReport,
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
export const useStudies = () => useQuery({ queryKey: ['studies'], queryFn: client.studies, staleTime: Infinity })
export const useStudy = (id: string) => useQuery({ queryKey: ['study', id], queryFn: () => client.study(id), staleTime: Infinity })

/** Every pool study that has been run, narrowest first (flagships, then every model). */
export function useStudyReports(): PoolStudyReport[] {
  const flagship = useStudy('flagship')
  const wide = useStudy('wide')
  return [flagship.data, wide.data].filter((item): item is PoolStudyReport => Boolean(item))
}

/** The widest study: the one whose charts cover the most models. */
export const widest = (studies: PoolStudyReport[]) => studies[studies.length - 1]

export const addedLabel: Record<string, string> = { flagship: 'Flagship', budget: 'Budget' }
export const studyRouterName: Record<string, string> = { flagship: 'Router + flagships', wide: 'Router · every model' }
export const usePool = () => useQuery({ queryKey: ['learned-pool'], queryFn: client.learnedPool, staleTime: Infinity })
/** Every prompt of an evaluation, with each model's outcome and each strategy's choice. */
export const usePrompts = (evaluation: ExplorerEvaluation, enabled = true) =>
  useQuery({ queryKey: ['prompts', evaluation], queryFn: () => client.prompts(evaluation), staleTime: Infinity, enabled })
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
  /** Added in a pool study ("flagship", "budget"): reached by a study's router, not the frozen one. */
  added: string | null
}

export function modelViews(
  pool: PoolSnapshot | null | undefined,
  catalog: LiveCatalogStatus | null | undefined,
  learned: LearnedRouterReport | null | undefined,
  final: FinalEvaluationReport | null | undefined,
  studies: PoolStudyReport[] = [],
): ModelView[] {
  if (!pool) return []
  const status = new Map(catalog?.models.map((item) => [item.model_id, item]))
  const fresh = new Map(final?.evaluations.find((item) => item.evaluation_id === 'final')?.matrix.map((row) => [row.model_id, row]))
  const suite = new Map(learned?.matrix.map((row) => [row.model_id, row]))
  const routed = new Set(learned?.models ?? [])
  const views: ModelView[] = pool.models.map((model) => ({
    id: model.id,
    pool: model,
    status: status.get(model.id),
    inRouter: routed.size === 0 || routed.has(model.id),
    fresh: fresh.get(model.id),
    suite: suite.get(model.id),
    added: null,
  }))
  const seen = new Set(views.map((view) => view.id))
  // The widest study first, so each added model takes its numbers from the largest pool.
  for (const study of [...studies].reverse()) {
    const studyFresh = new Map(study.evaluations.find((item) => item.evaluation_id === 'final')?.matrix.map((row) => [row.model_id, row]))
    const studySuite = new Map(study.suite_matrix.map((row) => [row.model_id, row]))
    for (const model of study.added) {
      if (seen.has(model.id)) continue
      seen.add(model.id)
      views.push({ id: model.id, pool: model, status: status.get(model.id), inRouter: false, fresh: studyFresh.get(model.id), suite: studySuite.get(model.id), added: study.added_from[model.id] ?? 'flagship' })
    }
  }
  return views
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
