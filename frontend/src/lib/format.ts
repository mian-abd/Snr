import type { Interval } from '../api/types'

export const usd = (value: number) => {
  if (value === 0) return '$0'
  if (Math.abs(value) < 0.001) return `$${value.toFixed(5)}`
  if (Math.abs(value) < 0.1) return `$${value.toFixed(4)}`
  return `$${value.toFixed(2)}`
}
export const usdOrFree = (value: number) => (value === 0 ? 'Free' : usd(value))
export const perMillion = (value: number) => (value === 0 ? 'Free' : `$${Number(value.toPrecision(3))}`)
export const pct = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`
export const seconds = (ms: number | null | undefined) => (ms == null ? '—' : `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`)
export const count = (value: number) => value.toLocaleString('en-US')
export const tokens = (value: number) => value.toLocaleString('en-US')
export const signed = (value: number, format: (value: number) => string) =>
  `${value > 0 ? '+' : value < 0 ? '−' : '±'}${format(Math.abs(value))}`
export const span = (interval: Interval | null | undefined, format: (value: number) => string) =>
  interval ? `${format(interval.low)} – ${format(interval.high)}` : '—'
export const pValue = (value: number) => (value < 0.001 ? '< 0.001' : value.toFixed(3))
export const shortDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'
export const shortTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'never'
