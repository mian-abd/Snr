import { ApiError } from '../api/client'
import type { Health } from '../api/types'

/** Live calls this visitor can still make today on a public demo, or null on a private server. */
export function liveCallsLeft(health: Health | undefined): number | null {
  if (!health?.public_mode) return null
  return Math.max(0, Math.min(health.live_calls_left ?? 0, health.client_live_calls_left ?? 0))
}

export function liveCallsNote(health: Health | undefined): string | null {
  const left = liveCallsLeft(health)
  if (left === null) return null
  return `Public demo: ${left} live ${left === 1 ? 'call' : 'calls'} left today. Previews are unlimited.`
}

/** A 429 (allowance used) or 403 (call too costly, or a tool turned off) is a limit, not a fault. */
export function isLimitNotice(error: Error): boolean {
  return error instanceof ApiError && (error.status === 429 || error.status === 403)
}
