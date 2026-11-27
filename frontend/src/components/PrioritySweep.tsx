import { useState } from 'react'
import type { PrioritySweepPoint } from '../api/types'
import { ShareBars } from '../charts/Charts'
import styles from '../charts/explorers.module.css'
import { dollarTick, linearScale, logScale } from '../charts/scales'
import { SweepChart, type SweepPoint } from '../charts/SweepChart'
import { pct, seconds, usd, usdOrFree } from '../lib/format'
import { modelColors } from '../lib/makers'
import { ChartCard, ModelLogo, Segmented } from '../ui'
import ui from '../ui/ui.module.css'

type Axis = 'cost' | 'latency'

const weightName: Record<Axis, string> = { cost: 'Cost weight', latency: 'Speed weight' }
const costOf = (point: PrioritySweepPoint) => point.total_cost_usd
const timeOf = (point: PrioritySweepPoint) => point.median_latency_ms ?? 0

/** The smallest weight that gets 90% of the way from the first setting's cost (or time) to the last one's. */
function knee(points: PrioritySweepPoint[], axis: Axis) {
  const measure = axis === 'cost' ? costOf : timeOf
  const start = measure(points[0])
  const end = measure(points[points.length - 1])
  if (start <= end) return 0
  const target = start - (start - end) * 0.9
  return Math.max(0, points.findIndex((point) => measure(point) <= target + 1e-12))
}

function versus(diff: number, format: (value: number) => string, less: string, more: string) {
  if (Math.abs(diff) < 1e-9) return 'Same as at weight 0'
  return `${format(Math.abs(diff))} ${diff < 0 ? less : more} than at weight 0`
}

/**
 * The priority sweep as one explorer: pick which weight to turn up, read accuracy against cost
 * or time, and pick a weight on the slider (or click a point) to see its numbers and the models
 * it used.
 */
export function PrioritySweep({ sweep, prompts, models }: { sweep: PrioritySweepPoint[]; prompts: number; models: Array<{ id: string; name: string }> }) {
  const axes = (['cost', 'latency'] as const).filter((axis) => sweep.some((point) => point.axis === axis))
  const [chosenAxis, setAxis] = useState<Axis>('cost')
  const [xMeasure, setXMeasure] = useState<Axis>('cost')
  const [picked, setPicked] = useState<Partial<Record<Axis, number>>>({})
  const axis = axes.includes(chosenAxis) ? chosenAxis : axes[0]
  const points = sweep.filter((point) => point.axis === axis).sort((a, b) => a.weight - b.weight)
  if (!axis || !points.length) return null

  const name = weightName[axis]
  const best = knee(points, axis)
  const pickedIndex = points.findIndex((point) => point.weight === picked[axis])
  const selected = pickedIndex >= 0 ? pickedIndex : best
  const point = points[selected]
  const first = points[0]
  const x = (item: PrioritySweepPoint) => (xMeasure === 'cost' ? costOf(item) : timeOf(item) / 1000)
  const chartPoints: SweepPoint[] = points.map((item) => ({
    weight: item.weight,
    x: x(item),
    y: item.accuracy * 100,
    details: [`${item.correct} of ${prompts} right (${pct(item.accuracy)})`, `${usdOrFree(item.total_cost_usd)} billed · median ${seconds(item.median_latency_ms)}`],
  }))
  const xScale = xMeasure === 'cost'
    ? logScale(chartPoints.map((item) => item.x), dollarTick)
    : linearScale(chartPoints.map((item) => item.x), { format: (value) => `${Number(value.toFixed(1))} s`, minSpan: 2, floor: 0 })
  const yScale = linearScale(chartPoints.map((item) => item.y), { format: (value) => `${Number(value.toFixed(1))}%`, minSpan: 4, floor: 0, ceil: 100 })

  const names = new Map(models.map((model) => [model.id, model.name]))
  const known = models.map((model) => model.id)
  const colors = modelColors([...known, ...new Set(sweep.flatMap((item) => Object.keys(item.selected_models)).filter((id) => !known.includes(id)))])
  const chosen = Object.entries(point.selected_models).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1])
  const total = chosen.reduce((sum, [, n]) => sum + n, 0)
  const pickName = `${name} ${point.weight}`
  const other = axis === 'cost' ? 'speed' : 'cost'
  const choose = (index: number) => setPicked({ ...picked, [axis]: points[index].weight })
  const topModel = (item: PrioritySweepPoint) => {
    const entries = Object.entries(item.selected_models).sort((a, b) => b[1] - a[1])
    const sum = entries.reduce((acc, [, n]) => acc + n, 0)
    return entries.length ? `${names.get(entries[0][0]) ?? entries[0][0]} · ${Math.round((entries[0][1] / sum) * 100)}%` : '—'
  }

  return (
    <ChartCard metric={xMeasure === 'cost' ? 'cost' : 'speed'} title={`Turning up the ${axis === 'cost' ? 'cost' : 'speed'} weight`}
      subtitle={`Right answers against ${xMeasure === 'cost' ? `billed cost for all ${prompts} prompts, on a log scale with free at the left` : `median response time across ${prompts} prompts`}. Each point is one weight; the line follows the weight from 0 up.`}
      tools={(
        <>
          {axes.length > 1 && <Segmented label="Weight to turn up" value={axis} onChange={(next) => { setAxis(next); setXMeasure(next) }} options={axes.map((id) => ({ id, label: weightName[id] }))} />}
          <Segmented label="Plot against" value={xMeasure} onChange={setXMeasure} options={[{ id: 'cost', label: 'Billed cost' }, { id: 'latency', label: 'Median time' }]} />
        </>
      )}
      footnotes={[{
        title: `Every ${name.toLowerCase()} in a table`,
        body: (
          <div className={ui.tableWrap}>
            <table className={ui.table} aria-label={`Priority sweep: ${name.toLowerCase()}`}>
              <thead><tr><th>{name}</th><th>Right answers</th><th>Billed cost</th><th>Median time</th><th>Most used</th></tr></thead>
              <tbody>{points.map((item, index) => (
                <tr key={item.weight} className={index === selected ? ui.selectedRow : undefined}>
                  <td className={ui.num}>{item.weight}</td>
                  <td className={ui.num}>{item.correct}/{prompts}</td>
                  <td className={ui.num}>{usdOrFree(item.total_cost_usd)}</td>
                  <td className={ui.num}>{seconds(item.median_latency_ms)}</td>
                  <td>{topModel(item)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ),
      }]}>
      <div className={styles.sweepGrid}>
        <div>
          <SweepChart points={chartPoints} selected={selected} onSelect={choose} xScale={xScale} yScale={yScale} weightName={name}
            xLabel={xMeasure === 'cost' ? 'Billed cost for all prompts (USD, log scale)' : 'Median response time (s)'} yLabel="Right answers"
            label={`Right answers against ${xMeasure === 'cost' ? 'billed cost' : 'median time'} as the ${name.toLowerCase()} rises from ${first.weight} to ${points[points.length - 1].weight}. The numbers are in the table below the chart.`} />
          <label className={styles.slider}>
            <span>Pick a {name.toLowerCase()}<b>{point.weight}</b></span>
            <input type="range" min={0} max={points.length - 1} step={1} value={selected} aria-label={name} aria-valuetext={`${point.weight}`}
              onChange={(event) => choose(Number(event.target.value))} />
            <span className={styles.sliderEnds}><span>{first.weight}</span><span>{points[points.length - 1].weight}</span></span>
          </label>
        </div>
        <div className={styles.readout} aria-live="polite">
          <div className={styles.readoutHead}>
            <span>{name}</span>
            <strong>{point.weight}</strong>
            <p>Accuracy has weight 1 and the {other} weight is 0.{selected === best && selected > 0 ? ` Most of the ${axis === 'cost' ? 'saving' : 'speed-up'} has arrived by this weight.` : ''}</p>
          </div>
          <dl className={styles.facts}>
            <div><dt>Right answers</dt><dd>{point.correct}/{prompts}</dd><dd className={styles.note}>{pct(point.accuracy)} · {versus(point.correct - first.correct, (n) => `${n}`, 'fewer', 'more')}</dd></div>
            <div><dt>Billed cost</dt><dd>{usdOrFree(point.total_cost_usd)}</dd><dd className={styles.note}>{versus(point.total_cost_usd - first.total_cost_usd, usd, 'less', 'more')}</dd></div>
            <div><dt>Median time</dt><dd>{seconds(point.median_latency_ms)}</dd><dd className={styles.note}>{versus(timeOf(point) - timeOf(first), (ms) => seconds(ms), 'faster', 'slower')}</dd></div>
          </dl>
          <div className={styles.picks}>
            <strong>Where the prompts went</strong>
            {chosen.length ? (
              <>
                <ShareBars label={`Models chosen at ${pickName.toLowerCase()}`} colors={colors}
                  rows={[{ id: 'picked', label: pickName, segments: chosen.map(([id, n]) => ({ id, name: names.get(id) ?? id, share: n / total })) }]} />
                <ul className={styles.pickList}>
                  {chosen.map(([id, n]) => (
                    <li key={id}>
                      <i style={{ background: colors.get(id) ?? 'var(--maker-other)' }} aria-hidden="true" />
                      <ModelLogo id={id} size={16} local={id.includes('local')} />
                      <span>{names.get(id) ?? id}</span>
                      <small>{n} · {Math.round((n / total) * 100)}%</small>
                    </li>
                  ))}
                </ul>
              </>
            ) : <span className={ui.muted}>No choices were recorded for this weight.</span>}
          </div>
        </div>
      </div>
    </ChartCard>
  )
}
