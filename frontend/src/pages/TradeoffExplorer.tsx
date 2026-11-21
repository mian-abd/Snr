import { useState } from 'react'
import type { EvaluationSet, PoolStudyReport, RoutingPriority } from '../api/types'
import { ScatterLegend, TradeoffScatter, type TradeoffPoint } from '../charts/TradeoffScatter'
import { find, priorityLabel, studyRouterName } from '../lib/data'
import { detailLines, fleetRows } from '../lib/fleet'
import { makersIn } from '../lib/makers'
import { ChartCard, Segmented } from '../ui'
import styles from './home.module.css'

type Axis = 'cost' | 'time'
const shown: RoutingPriority[] = ['quality', 'cost', 'latency']
const poolName: Record<string, string> = { standard: 'Standard', flagship: 'With flagships', wide: 'Every model' }

/** Accuracy against cost or time, for the standard pool or a pool study's wider one. */
export function TradeoffExplorer({ fresh, studies }: { fresh: EvaluationSet; studies: PoolStudyReport[] }) {
  const [axis, setAxis] = useState<Axis>('cost')
  const [pool, setPool] = useState<string>(studies.length ? studies[studies.length - 1].study_id : 'standard')
  const study = studies.find((item) => item.study_id === pool)
  const evaluation = study?.evaluations.find((item) => item.evaluation_id === 'final') ?? fresh
  const router = study ? studyRouterName[study.study_id] ?? 'Study router' : 'Router'
  const models = fleetRows(evaluation.matrix).filter((row) => row.served)
  const x = (cost: number, latencyMs: number | null) => (axis === 'cost' ? cost : (latencyMs ?? 0) / 1000)
  const points: TradeoffPoint[] = [
    ...models.map((row) => ({ id: row.id, label: row.name, kind: 'model' as const, modelId: row.id, x: x(row.cost, row.latencyMs), y: row.accuracy * 100, details: detailLines(row.correct, row.prompts, row.cost, row.latencyMs) })),
    ...shown.flatMap((priority) => {
      const strategy = find(evaluation.strategies, `learned:${priority}`)
      return strategy ? [{ id: strategy.strategy_id, label: `${router} · ${priorityLabel[priority]}`, kind: 'router' as const, x: x(strategy.total_cost_usd, strategy.median_latency_ms), y: strategy.accuracy * 100, details: detailLines(strategy.correct, strategy.prompts, strategy.total_cost_usd, strategy.median_latency_ms) }] : []
    }),
  ]
  const title = axis === 'cost' ? 'Accuracy against cost' : 'Accuracy against response time'
  return (
    <ChartCard metric={axis === 'cost' ? 'cost' : 'speed'} title={title}
      subtitle={axis === 'cost'
        ? `Right answers and billed cost for all ${evaluation.prompts} fresh prompts · cost on a log scale, free at the left`
        : `Right answers and median seconds per prompt on ${evaluation.prompts} fresh prompts`}
      tools={
        <div className={styles.controls}>
          <Segmented label="Measure" value={axis} onChange={setAxis} options={[{ id: 'cost', label: 'Cost' }, { id: 'time', label: 'Time' }]} />
          {studies.length > 0 && (
            <Segmented label="Pool" value={pool} onChange={setPool}
              options={[{ id: 'standard', label: poolName.standard }, ...studies.map((item) => ({ id: item.study_id, label: poolName[item.study_id] ?? item.title }))]} />
          )}
        </div>
      }>
      {axis === 'cost'
        ? <TradeoffScatter key={`cost-${pool}`} points={points} xScale="symlog" frontier label={title} xLabel="Cost for all prompts (USD, log scale)" yLabel="Right answers"
            formatX={(value) => (value === 0 ? 'Free' : value < 1 ? `$${Number(value.toPrecision(1))}` : `$${value}`)} />
        : <TradeoffScatter key={`time-${pool}`} points={points} frontier label={title} xLabel="Median response time (seconds)" yLabel="Right answers"
            formatX={(value) => `${Number(value.toFixed(1))} s`} />}
      <div className={styles.legendRow}>
        <ScatterLegend items={[
          ...makersIn(models.map((row) => row.id)).map((maker) => ({ name: maker.name, color: maker.color, shape: 'dot' as const })),
          { name: study ? `${router}` : 'Adaptive router', shape: 'diamond' },
          { name: axis === 'cost' ? 'Cheapest at each accuracy' : 'Fastest at each accuracy', shape: 'line' },
        ]} />
      </div>
    </ChartCard>
  )
}
