import { expect, it } from 'vitest'
import { ApiError } from '../api/client'
import type { Health } from '../api/types'
import { isLimitNotice, liveCallsLeft, liveCallsNote } from './publicMode'

const health: Health = {
  status: 'ok', version: '0.1.0', registry_loaded: true, registry_snapshot_id: 's', routing_registry_snapshot_id: null,
  credential_configured: true, active_benchmark_run_id: null,
}

it('says nothing on a private server', () => {
  expect(liveCallsNote(undefined)).toBeNull()
  expect(liveCallsNote({ ...health, public_mode: false, live_calls_left: null, client_live_calls_left: null })).toBeNull()
})

it('counts the smaller of the shared and personal allowance', () => {
  expect(liveCallsLeft({ ...health, public_mode: true, live_calls_left: 2, client_live_calls_left: 6 })).toBe(2)
  expect(liveCallsNote({ ...health, public_mode: true, live_calls_left: 60, client_live_calls_left: 1 }))
    .toBe('Public demo: 1 live call left today. Previews are unlimited.')
  expect(liveCallsNote({ ...health, public_mode: true, live_calls_left: 0, client_live_calls_left: 0 }))
    .toBe('Public demo: 0 live calls left today. Previews are unlimited.')
})

it('treats 429 and 403 as limits and other failures as errors', () => {
  expect(isLimitNotice(new ApiError('used up', 429))).toBe(true)
  expect(isLimitNotice(new ApiError('too costly', 403))).toBe(true)
  expect(isLimitNotice(new ApiError('boom', 502))).toBe(false)
  expect(isLimitNotice(new Error('network'))).toBe(false)
})
