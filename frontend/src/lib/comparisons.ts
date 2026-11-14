import type { PairedComparison } from '../api/types'

export function verdict(item: PairedComparison) {
  if (item.holm_p < 0.05) {
    return item.accuracy_difference > 0
      ? { tone: 'good' as const, text: 'More accurate' }
      : { tone: 'bad' as const, text: 'Less accurate' }
  }
  return { tone: 'neutral' as const, text: 'No detectable difference' }
}

export function costLine(item: PairedComparison) {
  if (item.cost_ratio == null) return 'The comparison is free, so there is no cost ratio.'
  const ci = item.cost_ratio_ci
  if (ci && ci.high < 1) return `${Math.round((1 - item.cost_ratio) * 100)}% cheaper (95% interval ${Math.round((1 - ci.high) * 100)}–${Math.round((1 - ci.low) * 100)}%).`
  if (ci && ci.low > 1) return `${item.cost_ratio.toFixed(2)}× the cost.`
  return `Cost ratio ${item.cost_ratio.toFixed(2)}×, not clearly different.`
}

const signedSeconds = (ms: number) => `${ms > 0 ? '+' : ms < 0 ? '−' : '±'}${Math.abs(ms / 1000).toFixed(1)} s`

export function timeLine(item: PairedComparison) {
  if (!/:(latency|balanced)$/.test(item.strategy_id)) return ''
  const ci = item.median_latency_difference_ci
  const verdict = ci.high < 0 ? 'faster' : ci.low > 0 ? 'slower' : 'not clearly different'
  return ` Median time ${signedSeconds(item.median_latency_difference_ms)} (95% interval ${signedSeconds(ci.low)} to ${signedSeconds(ci.high)}), ${verdict}.`
}
