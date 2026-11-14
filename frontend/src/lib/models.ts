import type { PoolModel } from '../api/types'
import type { ModelView } from './data'

export const priceOf = (model: PoolModel) => ({
  input: Number(model.prompt_price_per_token) * 1e6,
  output: Number(model.completion_price_per_token) * 1e6,
})

export function changedPrice(view: ModelView) {
  const status = view.status
  if (!status || status.live_prompt_price_per_million == null || status.live_completion_price_per_million == null) return null
  const before = priceOf(view.pool)
  const moved = Math.abs(status.live_prompt_price_per_million - before.input) > 1e-9 || Math.abs(status.live_completion_price_per_million - before.output) > 1e-9
  return moved ? { input: status.live_prompt_price_per_million, output: status.live_completion_price_per_million } : null
}

export function availability(view: ModelView) {
  if (!view.inRouter) return { tone: 'neutral' as const, text: 'Not in the router' }
  if (!view.status) return { tone: 'neutral' as const, text: 'Not checked' }
  if (!view.status.available) return { tone: 'bad' as const, text: 'Unavailable' }
  return view.status.checked ? { tone: 'good' as const, text: 'Available' } : { tone: 'neutral' as const, text: 'Not checked' }
}
