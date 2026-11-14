import type { EvaluationSet, LearnedMatrixRow, LearnedStrategyOutcome } from '../api/types'
import { priorityLabel, priorityOrder, strategyLabel } from './data'
import { pct, seconds, usd } from './format'

/** One measured model on one prompt set, in the shape the leaderboard charts use. */
export type FleetRow = {
  id: string
  name: string
  access: string
  correct: number
  prompts: number
  accuracy: number
  cost: number
  latencyMs: number | null
  failed: number
  served: boolean
  local: boolean
  row: LearnedMatrixRow
}

export function fleetRows(matrix: LearnedMatrixRow[]): FleetRow[] {
  return matrix.map((row) => ({
    id: row.model_id,
    name: row.display_name.replace(/\s*\((free|local)\)/i, ''),
    access: row.access,
    correct: row.correct,
    prompts: row.prompts,
    accuracy: row.prompts ? row.correct / row.prompts : 0,
    cost: row.cost_usd,
    latencyMs: row.median_latency_ms,
    failed: row.failed_calls,
    served: row.failed_calls < row.prompts,
    local: row.access === 'local',
    row,
  }))
}

/** Routers worth showing next to the models: the adaptive router at each priority. */
export function routerRows(evaluation: EvaluationSet, priorities = priorityOrder.filter((id) => id !== 'balanced')) {
  return priorities
    .map((priority) => evaluation.strategies.find((item) => item.strategy_id === `learned:${priority}`))
    .filter((item): item is LearnedStrategyOutcome => Boolean(item))
}

export const routerName = (strategy: LearnedStrategyOutcome) => `Router · ${priorityLabel[strategy.strategy_id.split(':')[1] as keyof typeof priorityLabel] ?? strategyLabel(strategy.strategy_id)}`

export const detailLines = (correct: number, prompts: number, cost: number, latencyMs: number | null) => [
  `${correct} of ${prompts} right (${pct(prompts ? correct / prompts : 0)})`,
  `Cost for all prompts ${usd(cost)}`,
  `Median time ${seconds(latencyMs)}`,
]

/** Names joined for a sentence: "A", "A and B", "A, B and C". */
export function listNames(names: string[]) {
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}
