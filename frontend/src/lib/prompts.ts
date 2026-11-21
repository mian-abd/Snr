import type { ExplorerEvaluation, ExplorerModel, ExplorerPrompt, PromptOutcome, RoutingPriority } from '../api/types'
import { priorityLabel, priorityOrder, strategyFamily } from './data'
import { normalize } from './search'

/** How one model did on one prompt. A failed call counts as wrong, but is shown apart. */
export type Verdict = 'right' | 'wrong' | 'failed'

export const verdictOf = (outcome: PromptOutcome | undefined): Verdict =>
  outcome?.correct ? 'right' : outcome?.status === 'success' ? 'wrong' : 'failed'

export const verdictLabel: Record<Verdict, string> = { right: 'Right', wrong: 'Wrong', failed: 'Failed call' }

export const statusLabel: Record<string, string> = {
  success: 'Answered',
  provider_error: 'Provider error',
  timeout: 'Timed out',
  rate_limited: 'Rate limited',
  invalid_response: 'Unusable response',
  model_mismatch: 'Another model answered',
}

export const benchmarkOrder = ['gsm8k', 'mmlu_pro', 'humaneval_plus', 'mbpp_plus']
export const benchmarkLabel: Record<string, string> = { gsm8k: 'GSM8K', mmlu_pro: 'MMLU-Pro', humaneval_plus: 'HumanEval+', mbpp_plus: 'MBPP+' }

/** The quick filters, by what the models did on a prompt. */
export const shows = ['all', 'router-wrong', 'avoidable', 'none-right', 'one-right'] as const
export type Show = (typeof shows)[number]
export const showLabel: Record<Show, string> = {
  all: 'All',
  'router-wrong': 'Router wrong',
  avoidable: 'Router wrong, another model right',
  'none-right': 'No model right',
  'one-right': 'Only one model right',
}
export const showHint: Record<Show, string> = {
  all: 'Every prompt that matches the other filters',
  'router-wrong': 'The router’s pick for this priority was wrong or failed',
  avoidable: 'The router’s pick was wrong while another model it could choose was right',
  'none-right': 'Not one model answered right',
  'one-right': 'Exactly one model answered right',
}

export const pageSize = 25

/** The list's state, kept in the address so a filtered view can be linked and comes back. */
export type PromptFilters = {
  set: ExplorerEvaluation
  task: string
  bench: string
  show: Show
  q: string
  priority: RoutingPriority
  page: number
}

export const defaultFilters: PromptFilters = { set: 'final', task: 'all', bench: 'all', show: 'all', q: '', priority: 'quality', page: 1 }

export function readFilters(query: URLSearchParams): PromptFilters {
  const pick = <T extends string>(key: string, allowed: readonly T[], fallback: T) => {
    const value = query.get(key) as T | null
    return value && allowed.includes(value) ? value : fallback
  }
  const page = Number.parseInt(query.get('page') ?? '', 10)
  return {
    set: pick<ExplorerEvaluation>('set', ['final', 'cp3_test'], 'final'),
    task: pick('task', ['all', 'math', 'qa', 'code'], 'all'),
    bench: pick('bench', ['all', ...benchmarkOrder], 'all'),
    show: pick('show', shows, 'all'),
    q: query.get('q') ?? '',
    priority: pick('priority', priorityOrder, 'quality'),
    page: Number.isFinite(page) && page > 1 ? page : 1,
  }
}

/** The filters as a query string, leaving out the defaults. */
export function filterQuery(filters: PromptFilters) {
  const params = new URLSearchParams()
  for (const key of Object.keys(defaultFilters) as Array<keyof PromptFilters>) {
    if (filters[key] !== defaultFilters[key]) params.set(key, String(filters[key]))
  }
  return params.toString()
}

export const listHref = (filters: PromptFilters) => {
  const query = filterQuery(filters)
  return query ? `/prompts?${query}` : '/prompts'
}

export const promptHref = (id: string, filters: PromptFilters) => {
  const query = filterQuery(filters)
  return `/prompts/${encodeURIComponent(id)}${query ? `?${query}` : ''}`
}

/** The model the adaptive router chose for this prompt under a priority. */
export const routerPick = (prompt: ExplorerPrompt, priority: RoutingPriority) => prompt.choices[`learned:${priority}`]

export const rightCount = (prompt: ExplorerPrompt, models: ExplorerModel[]) =>
  models.filter((model) => prompt.outcomes[model.model_id]?.correct).length

export function matchesShow(prompt: ExplorerPrompt, models: ExplorerModel[], show: Show, priority: RoutingPriority) {
  if (show === 'all') return true
  if (show === 'router-wrong' || show === 'avoidable') {
    const pick = routerPick(prompt, priority)
    if (pick == null || prompt.outcomes[pick]?.correct) return false
    // Only the frozen pool counts: the models added later were never the router's to choose.
    return show === 'router-wrong' || models.some((model) => !model.added_from && model.model_id !== pick && prompt.outcomes[model.model_id]?.correct)
  }
  const right = rightCount(prompt, models)
  return show === 'none-right' ? right === 0 : right === 1
}

/** The text a search looks in: the prompt, its options, its ID, and its subject. */
export const searchText = (prompt: ExplorerPrompt) =>
  normalize(`${prompt.sample_id} ${prompt.category ?? ''} ${prompt.question} ${prompt.options.join(' ')}`)

export const searchWords = (query: string) => normalize(query).split(/\s+/).filter(Boolean)

/**
 * The prompts the filters keep. `texts` holds each prompt's searchable text (see searchText);
 * pass `show: 'all'` to get the set the quick filters count over.
 */
export function filterPrompts(prompts: ExplorerPrompt[], models: ExplorerModel[], filters: PromptFilters, texts: Map<string, string>) {
  const words = searchWords(filters.q)
  return prompts.filter((prompt) =>
    (filters.task === 'all' || prompt.task_group === filters.task)
    && (filters.bench === 'all' || prompt.benchmark === filters.bench)
    && (!words.length || words.every((word) => (texts.get(prompt.sample_id) ?? '').includes(word)))
    && matchesShow(prompt, models, filters.show, filters.priority))
}

/** A one-line preview: for code, the docstring says more than the imports and signature. */
export function excerpt(prompt: ExplorerPrompt) {
  let text = prompt.question
  if (prompt.task_group === 'code') {
    const doc = /("""|''')([\s\S]*?)\1/.exec(text)
    if (doc && doc[2].trim()) text = doc[2]
  }
  return text.replace(/\s+/g, ' ').trim()
}

/** The letter of the n-th multiple-choice option (A first). */
export const optionLetter = (index: number) => String.fromCharCode(65 + index)

const fixedShort: Record<string, string> = {
  fixed_cheapest: 'Always cheapest',
  fixed_strongest: 'Always strongest',
  rule_balanced: 'Rule-based',
  rule_balanced_no_catalog: 'Rule-based, no live check',
}
const familyShort: Record<string, string> = {
  learned: 'Router',
  learned_no_catalog: 'Router, no live check',
  model_task_prior: 'Task averages',
  oracle: 'Hindsight',
}

/** A strategy's name short enough for a badge (strategyLabel gives the full one). */
export function shortStrategy(id: string) {
  if (fixedShort[id]) return fixedShort[id]
  const [family, priority] = id.split(':')
  const name = familyShort[family] ?? family
  return priority ? `${name} · ${priorityLabel[priority as RoutingPriority] ?? priority}` : name
}

const familyRank = ['learned', 'fixed', 'rule', 'learned_no_catalog', 'model_task_prior', 'oracle']

/** Router first, then the baselines, then the references; priorities in their usual order. */
export function strategyRank(id: string) {
  const at = familyRank.indexOf(strategyFamily(id))
  const priority = priorityOrder.indexOf(id.split(':')[1] as RoutingPriority)
  return (at < 0 ? familyRank.length : at) * 10 + (id.endsWith('no_catalog') ? 5 : 0) + Math.max(0, priority)
}
