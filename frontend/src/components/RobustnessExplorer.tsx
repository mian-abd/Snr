import { useState } from 'react'
import type { RobustnessReport, RoutingPriority, ScenarioStrategy } from '../api/types'
import { Dumbbell, type DumbbellRow } from '../charts/Dumbbell'
import { dollarTick, linearScale, logScale } from '../charts/scales'
import { priorityLabel } from '../lib/data'
import { pct, seconds, usd, usdOrFree } from '../lib/format'
import { ChartCard, Segmented } from '../ui'
import styles from '../charts/explorers.module.css'

type Measure = 'accuracy' | 'cost'

const result = (item: ScenarioStrategy, prompts: number) => `${item.correct}/${prompts} right · ${usdOrFree(item.total_cost_usd)} · ${seconds(item.median_latency_ms)}`
const spoken = (item: ScenarioStrategy, prompts: number) => `${item.correct} of ${prompts} right for ${usdOrFree(item.total_cost_usd)}, median ${seconds(item.median_latency_ms)}`
const changed = (value: number | null) => (value == null ? 'not counted' : `${value}`)

function delta(measure: Measure, told: ScenarioStrategy, old: ScenarioStrategy): DumbbellRow['delta'] {
  if (measure === 'accuracy') {
    const diff = told.correct - old.correct
    if (diff === 0) return { text: 'Same', tone: 'same' }
    return { text: `${diff > 0 ? '+' : '−'}${Math.abs(diff)} right`, tone: diff > 0 ? 'good' : 'bad' }
  }
  // Spending more is not a failure here (the told router may pay to get answers right), so cost stays uncolored.
  const diff = told.total_cost_usd - old.total_cost_usd
  if (Math.abs(diff) < 0.00005) return { text: 'Same', tone: 'same' }
  return { text: `${diff > 0 ? '+' : '−'}${usd(Math.abs(diff))}`, tone: 'plain' }
}

/**
 * Every scenario as a dumbbell: the router told about the change against the one keeping its
 * old estimates, for one priority, measured in right answers or in billed cost.
 */
export function RobustnessExplorer({ robustness, priority }: { robustness: RobustnessReport; priority: RoutingPriority }) {
  const [measure, setMeasure] = useState<Measure>('accuracy')
  const rows: DumbbellRow[] = robustness.scenarios.flatMap(({ scenario, prompts, strategies }) => {
    const told = strategies.find((item) => item.strategy_id === `learned:${priority}`)
    const old = strategies.find((item) => item.strategy_id === `learned_frozen:${priority}`)
    if (!told || !old) return []
    const value = (item: ScenarioStrategy) => (measure === 'accuracy' ? (item.correct / prompts) * 100 : item.total_cost_usd)
    return [{
      id: scenario.scenario_id,
      label: scenario.title,
      flag: scenario.observed ? 'Really happened' : undefined,
      a: value(told),
      b: value(old),
      delta: delta(measure, told, old),
      details: [
        scenario.title,
        `Told: ${result(told, prompts)}`,
        `Old estimates: ${result(old, prompts)}`,
        `Choices changed: ${changed(told.changed_decisions)} told, ${changed(old.changed_decisions)} with old estimates`,
      ],
      summary: `${scenario.title}${scenario.observed ? ', really happened' : ''}. Told about the change: ${spoken(told, prompts)}. Old estimates: ${spoken(old, prompts)}. ${changed(told.changed_decisions)} choices changed when told.`,
    }]
  })
  const values = rows.flatMap((row) => [row.a, row.b])
  const scale = measure === 'accuracy'
    ? linearScale(values, { format: (value) => `${Math.round(value)}%`, minSpan: 10, floor: 0, ceil: 100 })
    : logScale(values, dollarTick)
  const name = priorityLabel[priority]
  return (
    <ChartCard metric={measure === 'accuracy' ? 'accuracy' : 'cost'} title="Told about the change, or not"
      subtitle={measure === 'accuracy'
        ? `${name} setting · share of the ${robustness.prompts} prompts answered right under each change`
        : `${name} setting · billed cost for all ${robustness.prompts} prompts under each change, on a log scale with free at the left`}
      tools={<Segmented label="Measure" value={measure} onChange={setMeasure} options={[{ id: 'accuracy', label: 'Right answers' }, { id: 'cost', label: 'Billed cost' }]} />}>
      {rows.length ? (
        <>
          <Dumbbell rows={rows} scale={scale} series={['Router told about the change', 'Router with its old estimates']}
            label={`Robustness, ${measure === 'accuracy' ? 'right answers' : 'billed cost'}, ${name} setting: the router told about each change against the one with its old estimates`}
            deltaLabel="Told vs old"
            axisLabel={measure === 'accuracy' ? `Right answers (share of ${robustness.prompts} prompts)` : 'Billed cost for all prompts (USD, log scale)'} />
          <p className={styles.chartNote}>Hover or focus a row for both results and how many choices changed. {measure === 'accuracy' ? `One right answer is ${pct(1 / robustness.prompts)} of the prompts.` : 'A lower cost is better; free sits at the left edge.'}</p>
        </>
      ) : (
        <p className={styles.chartNote}>No scenario results for the {name.toLowerCase()} setting on this prompt set.</p>
      )}
    </ChartCard>
  )
}
