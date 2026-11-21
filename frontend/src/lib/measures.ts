import type { LearnedMatrixRow } from '../api/types'
import type { ModelView } from './data'

/** How many models the compare page shows side by side. */
export const maxCompared = 4

export const taskOrder = ['math', 'qa', 'code'] as const
export const taskLabel: Record<string, string> = { math: 'Math', qa: 'Knowledge', code: 'Code' }
export const taskBenchmark: Record<string, string> = { math: 'GSM8K', qa: 'MMLU-Pro', code: 'HumanEval+, MBPP+' }

/** A model answered at least one prompt of this set (a model that failed every call has no score). */
export const answered = (row: LearnedMatrixRow | undefined): row is LearnedMatrixRow => Boolean(row && row.prompts && row.failed_calls < row.prompts)
export const served = (view: ModelView) => answered(view.fresh)

/** Share right overall, or null when the model has no answers on that set. */
export const shareOf = (row: LearnedMatrixRow | undefined) => (answered(row) ? row.correct / row.prompts : null)

/** Share right on one task, or null when the set has no prompts of it or the model no answers. */
export function taskShareOf(row: LearnedMatrixRow | undefined, task: string) {
  const n = row?.prompts_by_task[task] ?? 0
  return answered(row) && n ? (row.correct_by_task[task] ?? 0) / n : null
}

export const freshShare = (view: ModelView) => shareOf(view.fresh)
export const taskShare = (view: ModelView, task: string) => taskShareOf(view.fresh, task)

export const contextLabel = (tokens: number) => (tokens >= 1_000_000 ? `${Math.round(tokens / 100_000) / 10}M` : `${Math.round(tokens / 1000)}K`)

export const plainName = (name: string) => name.replace(/\s*\((free|local)\)/i, '')

/** The compare page for these models (the URL is the shareable selection). */
export const compareHref = (ids: string[]) => (ids.length ? `/compare?models=${ids.map(encodeURIComponent).join(',')}` : '/compare')

/** Model IDs from the compare URL: trimmed, without repeats, at most four. */
export function parseCompared(value: string | null): string[] {
  const ids = (value ?? '').split(',').map((id) => id.trim()).filter(Boolean)
  return [...new Set(ids)].slice(0, maxCompared)
}

/** Change the address without a new history entry or a jump to the top, and tell the router. */
export function replaceRoute(path: string) {
  window.history.replaceState(window.history.state, '', `#${path}`)
  window.dispatchEvent(new Event('hashchange'))
}
