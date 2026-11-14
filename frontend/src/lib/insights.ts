import type { EvaluationSet } from '../api/types'
import { find } from './data'
import { pct, usd } from './format'

export function highlights(evaluation: EvaluationSet) {
  const s = evaluation.strategies
  const items: Array<{ label: string; value: string; text: string }> = []
  const [lq, fs, lc, fc, ll, ln] = ['learned:quality', 'fixed_strongest', 'learned:cost', 'fixed_cheapest', 'learned:latency', 'learned_no_catalog:latency'].map((id) => find(s, id))
  if (lq && fs && fs.total_cost_usd > 0) {
    const saved = 1 - lq.total_cost_usd / fs.total_cost_usd
    items.push({
      label: 'Best quality, for less',
      value: `${Math.round(saved * 100)}% cheaper`,
      text: `${lq.correct} of ${lq.prompts} right for ${usd(lq.total_cost_usd)}, against ${fs.correct} for ${usd(fs.total_cost_usd)} when every prompt goes to the strongest model.`,
    })
  }
  if (lc && fc) {
    items.push({
      label: 'Lowest cost',
      value: usd(lc.total_cost_usd),
      text: `${lc.correct} of ${lc.prompts} right, mostly on free models; always using the cheapest paid model gets ${fc.correct} for ${usd(fc.total_cost_usd)}.`,
    })
  }
  if (ll && ln) {
    items.push({
      label: 'A model was retired',
      value: `${ll.correct} vs ${ln.correct}`,
      text: `When the fastest model in the pool was retired, the live catalog check kept the Fastest priority at ${ll.correct} of ${ll.prompts} right; without it, calls went to the retired model and only ${ln.correct} were right.`,
    })
  }
  const oracle = evaluation.oracle.find((item) => item.strategy_id === 'oracle:quality')
  if (oracle && lq) {
    items.push({
      label: 'Room left',
      value: pct(oracle.accuracy, 0),
      text: `With perfect hindsight, a router could reach ${oracle.correct} of ${oracle.prompts} for ${usd(oracle.total_cost_usd)}. The gap is what better prompt signals could still win.`,
    })
  }
  return items
}
