import { useState } from 'react'
import styles from './charts.module.css'

export type ScatterPoint = { id: string; label: string; learned: boolean; oracle?: boolean; x: number; y: number; details: string[] }

type Props = { title: string; subtitle?: string; points: ScatterPoint[]; xLabel: string; formatX: (value: number) => string; yLabel?: string }

const WIDTH = 440
const HEIGHT = 290
const MARGIN = { top: 18, right: 14, bottom: 44, left: 46 }
const CHAR_WIDTH = 6.6 // px per character of the 12px label font
// Label offsets from a point: [dx, baseline dy, anchor]; the first clear one wins.
const OFFSETS: Array<[number, number, 'start' | 'end' | 'middle']> = [
  [9, -5, 'start'], [9, 15, 'start'], [-9, -5, 'end'], [-9, 15, 'end'], [0, -12, 'middle'], [0, 23, 'middle'],
  [6, -20, 'start'], [6, 30, 'start'], [-6, -20, 'end'], [-6, 30, 'end'],
]

type Box = { x0: number; y0: number; x1: number; y1: number }

function niceTicks(min: number, max: number, count: number) {
  const raw = (max - min || 1) / count
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((value) => value >= raw) ?? 10 * power
  const ticks: number[] = []
  for (let value = Math.ceil(min / step) * step; value <= max + step * 1e-6; value += step) ticks.push(Number(value.toFixed(10)))
  return ticks
}

const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1
const gap = (box: Box, x: number, y: number) => Math.hypot(Math.max(box.x0 - x, 0, x - box.x1), Math.max(box.y0 - y, 0, y - box.y1))

export function ScatterChart({ title, subtitle, points, xLabel, formatX, yLabel = 'Correct answers' }: Props) {
  const [active, setActive] = useState<string | null>(null)
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  const xMax = Math.max(...xs, 0) * 1.35 || 1 // room for labels right of the rightmost points
  const yLow = Math.max(0, Math.floor((Math.min(...ys) - 2) / 5) * 5)
  const yHigh = Math.min(100, Math.max(...ys) + 3)
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const sx = (value: number) => MARGIN.left + (value / xMax) * plotWidth
  const sy = (value: number) => MARGIN.top + (1 - (value - yLow) / (yHigh - yLow)) * plotHeight
  const frame: Box = { x0: MARGIN.left, y0: MARGIN.top, x1: WIDTH - MARGIN.right, y1: HEIGHT - MARGIN.bottom }

  const marks = points.map((point) => ({ point, px: sx(point.x), py: sy(point.y) }))
  const taken: Box[] = marks.map(({ px, py }) => ({ x0: px - 6, y0: py - 6, x1: px + 6, y1: py + 6 }))
  const labels = marks.filter(({ point }) => point.label).map(({ point, px, py }) => {
    const width = point.label.length * CHAR_WIDTH
    let best: { cost: number; dx: number; dy: number; anchor: 'start' | 'end' | 'middle'; box: Box } | null = null
    for (const [dx, dy, anchor] of OFFSETS) {
      const left = anchor === 'start' ? px + dx : anchor === 'end' ? px + dx - width : px - width / 2
      const box = { x0: left, y0: py + dy - 11, x1: left + width, y1: py + dy + 3 }
      const inside = box.x0 >= frame.x0 && box.x1 <= frame.x1 && box.y0 >= frame.y0 - 16 && box.y1 <= frame.y1
      const crowded = taken.some((other) => overlaps(box, other))
      // A label must sit nearer its own point than any other point, or it names the wrong one.
      const misleading = marks.some((other) => (other.px !== px || other.py !== py) && gap(box, other.px, other.py) < gap(box, px, py))
      const cost = (inside ? 0 : 100) + (crowded ? 10 : 0) + (misleading ? 5 : 0)
      if (!best || cost < best.cost) best = { cost, dx, dy, anchor, box }
      if (cost === 0) break
    }
    taken.push(best!.box)
    return { id: point.id, label: point.label, x: px + best!.dx, y: py + best!.dy, anchor: best!.anchor }
  })
  const current = marks.find(({ point }) => point.id === active)

  return (
    <figure className={styles.figure}>
      <figcaption><strong>{title}</strong>{subtitle && <span>{subtitle}</span>}</figcaption>
      <div className={styles.frame}>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${title}. Values are listed in the table below.`}>
          {niceTicks(yLow, yHigh, 4).map((tick) => (
            <g key={`y${tick}`}>
              <line className={styles.grid} x1={frame.x0} x2={frame.x1} y1={sy(tick)} y2={sy(tick)} />
              <text className={styles.tick} x={frame.x0 - 8} y={sy(tick) + 4} textAnchor="end">{tick}%</text>
            </g>
          ))}
          {niceTicks(0, xMax, 5).map((tick) => (
            <g key={`x${tick}`}>
              <line className={styles.grid} x1={sx(tick)} x2={sx(tick)} y1={frame.y0} y2={frame.y1} />
              <text className={styles.tick} x={sx(tick)} y={frame.y1 + 16} textAnchor="middle">{formatX(tick)}</text>
            </g>
          ))}
          <line className={styles.axis} x1={frame.x0} x2={frame.x1} y1={frame.y1} y2={frame.y1} />
          <text className={styles.axisLabel} x={frame.x0 + plotWidth / 2} y={HEIGHT - 6} textAnchor="middle">{xLabel}</text>
          <text className={styles.axisLabel} transform={`translate(12 ${frame.y0 + plotHeight / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
          {marks.filter(({ point }) => !point.learned && !point.oracle).map(({ point, px, py }) => <rect key={point.id} className={styles.markBaseline} x={px - 6} y={py - 6} width={12} height={12} rx={2} />)}
          {marks.filter(({ point }) => point.oracle).map(({ point, px, py }) => <path key={point.id} className={styles.markOracle} d={`M ${px} ${py - 7} L ${px + 7} ${py + 5} L ${px - 7} ${py + 5} Z`} />)}
          {marks.filter(({ point }) => point.learned).map(({ point, px, py }) => <circle key={point.id} className={styles.markLearned} cx={px} cy={py} r={5} />)}
          {labels.map((label) => <text key={label.id} className={styles.label} x={label.x} y={label.y} textAnchor={label.anchor}>{label.label}</text>)}
          {marks.map(({ point, px, py }) => (
            <circle
              key={`hit-${point.id}`} className={styles.hit} cx={px} cy={py} r={12} tabIndex={0}
              aria-label={[point.label || point.id, ...point.details].join(', ')}
              onPointerEnter={() => setActive(point.id)} onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(point.id)} onBlur={() => setActive(null)}
            />
          ))}
        </svg>
        {current && (
          <div className={styles.tooltip} style={{ left: `${(current.px / WIDTH) * 100}%`, top: `${(current.py / HEIGHT) * 100}%` }} role="status">
            <strong>{current.point.details[0]}</strong>
            <span>{current.point.label || points.find((item) => item.x === current.point.x && item.y === current.point.y && item.label)?.label}</span>
            {current.point.details.slice(1).map((line) => <span key={line}>{line}</span>)}
          </div>
        )}
      </div>
    </figure>
  )
}
