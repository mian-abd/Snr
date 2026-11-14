import { useState } from 'react'
import { makerOf } from '../lib/makers'
import styles from './charts.module.css'

export type TradeoffPoint = {
  id: string
  label: string
  kind: 'model' | 'router' | 'baseline' | 'oracle'
  /** For models: the maker color. */
  modelId?: string
  x: number
  y: number
  details: string[]
}

type Props = {
  points: TradeoffPoint[]
  xLabel: string
  yLabel: string
  formatX: (value: number) => string
  formatY?: (value: number) => string
  /** symlog shows free (zero) next to cents and dollars. */
  xScale?: 'linear' | 'symlog'
  /** The cheapest model for each accuracy level, as a dotted line. */
  frontier?: boolean
  /** Shade where a model is both cheaper (or faster) and more accurate than the median. */
  quadrant?: boolean
  label: string
  height?: number
}

const WIDTH = 760
const MARGIN = { top: 20, right: 20, bottom: 50, left: 54 }
const CHAR_WIDTH = 6.4
const OFFSETS: Array<[number, number, 'start' | 'end' | 'middle']> = [
  [10, 4, 'start'], [-10, 4, 'end'], [0, -11, 'middle'], [0, 20, 'middle'], [9, -8, 'start'], [9, 16, 'start'],
  [-9, -8, 'end'], [-9, 16, 'end'], [6, -20, 'start'], [-6, -20, 'end'], [6, 30, 'start'], [-6, 30, 'end'],
]
type Box = { x0: number; y0: number; x1: number; y1: number }
const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1
const gap = (box: Box, x: number, y: number) => Math.hypot(Math.max(box.x0 - x, 0, x - box.x1), Math.max(box.y0 - y, 0, y - box.y1))

function niceTicks(min: number, max: number, count: number) {
  const raw = (max - min || 1) / count
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((value) => value >= raw) ?? 10 * power
  const ticks: number[] = []
  for (let value = Math.ceil(min / step) * step; value <= max + step * 1e-6; value += step) ticks.push(Number(value.toFixed(10)))
  return ticks
}

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

/** Points no other point beats on both axes (lower x and higher y), left to right. */
function frontierOf(points: Array<{ x: number; y: number }>) {
  const sorted = [...points].sort((a, b) => a.x - b.x || b.y - a.y)
  const kept: Array<{ x: number; y: number }> = []
  for (const point of sorted) if (!kept.length || point.y > kept[kept.length - 1].y) kept.push(point)
  return kept
}

export function TradeoffScatter({ points, xLabel, yLabel, formatX, formatY = (value) => `${Math.round(value)}%`, xScale = 'linear', frontier = false, quadrant = false, label, height = 430 }: Props) {
  const [active, setActive] = useState<string | null>(null)
  if (!points.length) return null
  const positive = points.map((point) => point.x).filter((value) => value > 0)
  const minPositive = positive.length ? Math.min(...positive) : 1
  const offset = minPositive / 3
  const tx = (value: number) => (xScale === 'symlog' ? Math.log10(value + offset) : value)
  const xs = points.map((point) => tx(point.x))
  const ys = points.map((point) => point.y)
  const xLow = xScale === 'symlog' ? tx(0) : 0
  const xHigh = Math.max(...xs) + (Math.max(...xs) - xLow) * 0.16
  const yLow = Math.floor((Math.min(...ys) - 2) / 5) * 5
  const yHigh = Math.min(100, Math.ceil((Math.max(...ys) + 2) / 5) * 5)
  const plot = { x0: MARGIN.left, y0: MARGIN.top, x1: WIDTH - MARGIN.right, y1: height - MARGIN.bottom }
  const sx = (value: number) => plot.x0 + ((tx(value) - xLow) / (xHigh - xLow || 1)) * (plot.x1 - plot.x0)
  const sy = (value: number) => plot.y0 + (1 - (value - yLow) / (yHigh - yLow || 1)) * (plot.y1 - plot.y0)

  const xTicks = xScale === 'symlog'
    ? [0, ...Array.from({ length: 12 }, (_, i) => 10 ** (Math.floor(Math.log10(minPositive)) + i)).filter((value) => tx(value) <= xHigh && value >= minPositive / 10)]
    : niceTicks(0, xHigh, 5)
  const models = points.filter((point) => point.kind === 'model')
  const line = frontier ? frontierOf(models) : []
  const mx = quadrant && models.length > 2 ? median(models.map((point) => point.x)) : null
  const my = quadrant && models.length > 2 ? median(models.map((point) => point.y)) : null

  const marks = points.map((point) => ({ point, px: sx(point.x), py: sy(point.y) }))
  const taken: Box[] = marks.map(({ px, py }) => ({ x0: px - 7, y0: py - 7, x1: px + 7, y1: py + 7 }))
  // Routers first, so their labels get the best spots.
  const order = [...marks].sort((a, b) => Number(b.point.kind === 'router') - Number(a.point.kind === 'router'))
  const labels = order.filter(({ point }) => point.label).map(({ point, px, py }) => {
    const width = point.label.length * CHAR_WIDTH
    let best: { cost: number; dx: number; dy: number; anchor: 'start' | 'end' | 'middle'; box: Box } | null = null
    for (const [dx, dy, anchor] of OFFSETS) {
      const left = anchor === 'start' ? px + dx : anchor === 'end' ? px + dx - width : px - width / 2
      const box = { x0: left, y0: py + dy - 10, x1: left + width, y1: py + dy + 3 }
      const inside = box.x0 >= plot.x0 && box.x1 <= plot.x1 + 10 && box.y0 >= plot.y0 - 14 && box.y1 <= plot.y1
      const crowded = taken.some((other) => overlaps(box, other))
      const misleading = marks.some((other) => other.point.id !== point.id && gap(box, other.px, other.py) < gap(box, px, py))
      const cost = (inside ? 0 : 100) + (crowded ? 10 : 0) + (misleading ? 5 : 0)
      if (!best || cost < best.cost) best = { cost, dx, dy, anchor, box }
      if (cost === 0) break
    }
    taken.push(best!.box)
    return { id: point.id, label: point.label, x: px + best!.dx, y: py + best!.dy, anchor: best!.anchor, strong: point.kind === 'router' }
  })
  const current = marks.find(({ point }) => point.id === active)

  return (
    <div className={styles.scrollX}>
    <div className={`${styles.frame} ${styles.wide}`}>
      <svg viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={`${label}. The values are listed in the table.`}>
        {mx != null && my != null && (
          <rect className={styles.quadrant} x={plot.x0} y={plot.y0} width={Math.max(0, sx(mx) - plot.x0)} height={Math.max(0, sy(my) - plot.y0)} />
        )}
        {niceTicks(yLow, yHigh, 5).map((tick) => (
          <g key={`y${tick}`}>
            <line className={styles.grid} x1={plot.x0} x2={plot.x1} y1={sy(tick)} y2={sy(tick)} />
            <text className={styles.tick} x={plot.x0 - 10} y={sy(tick) + 4} textAnchor="end">{formatY(tick)}</text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <g key={`x${tick}`}>
            <line className={styles.grid} x1={sx(tick)} x2={sx(tick)} y1={plot.y0} y2={plot.y1} />
            <text className={styles.tick} x={sx(tick)} y={plot.y1 + 18} textAnchor="middle">{formatX(tick)}</text>
          </g>
        ))}
        <line className={styles.axis} x1={plot.x0} x2={plot.x1} y1={plot.y1} y2={plot.y1} />
        <text className={styles.axisLabel} x={(plot.x0 + plot.x1) / 2} y={height - 8} textAnchor="middle">{xLabel}</text>
        <text className={styles.axisLabel} transform={`translate(14 ${(plot.y0 + plot.y1) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
        {line.length > 1 && <path className={styles.frontier} d={line.map((point, index) => `${index ? 'L' : 'M'} ${sx(point.x)} ${sy(point.y)}`).join(' ')} />}
        {marks.map(({ point, px, py }) => {
          if (point.kind === 'model') return <circle key={point.id} className={styles.dot} cx={px} cy={py} r={6} style={{ fill: makerOf(point.modelId ?? point.id).color }} />
          if (point.kind === 'router') return <rect key={point.id} className={styles.diamond} x={px - 6} y={py - 6} width={12} height={12} transform={`rotate(45 ${px} ${py})`} />
          if (point.kind === 'oracle') return <path key={point.id} className={styles.triangle} d={`M ${px} ${py - 7} L ${px + 7} ${py + 5} L ${px - 7} ${py + 5} Z`} />
          return <rect key={point.id} className={styles.square} x={px - 5.5} y={py - 5.5} width={11} height={11} rx={1.5} />
        })}
        {labels.map((item) => <text key={`l-${item.id}`} className={item.strong ? styles.labelStrong : styles.label} x={item.x} y={item.y} textAnchor={item.anchor}>{item.label}</text>)}
        {marks.map(({ point, px, py }) => (
          <circle key={`hit-${point.id}`} className={styles.hit} cx={px} cy={py} r={12} tabIndex={0} aria-label={[point.label, ...point.details].join(', ')}
            onPointerEnter={() => setActive(point.id)} onPointerLeave={() => setActive(null)} onFocus={() => setActive(point.id)} onBlur={() => setActive(null)} />
        ))}
      </svg>
      {current && (
        <div className={styles.tooltip} style={{ left: `${(current.px / WIDTH) * 100}%`, top: `${(current.py / height) * 100}%` }} role="status">
          <strong>{current.point.label}</strong>
          {current.point.details.map((detail) => <span key={detail}>{detail}</span>)}
        </div>
      )}
    </div>
    </div>
  )
}

export function ScatterLegend({ items }: { items: Array<{ name: string; color?: string; shape: 'dot' | 'diamond' | 'square' | 'triangle' | 'line' | 'area' }> }) {
  return (
    <div className={styles.legend}>
      {items.map((item) => (
        <span key={item.name}>
          <svg width="14" height="12" aria-hidden="true">
            {item.shape === 'dot' && <circle cx="7" cy="6" r="4.5" style={{ fill: item.color }} />}
            {item.shape === 'diamond' && <rect x="3" y="2" width="8" height="8" transform="rotate(45 7 6)" className={styles.diamond} />}
            {item.shape === 'square' && <rect x="2.5" y="1.5" width="9" height="9" rx="1.5" className={styles.square} />}
            {item.shape === 'triangle' && <path d="M7 1 L12.5 11 L1.5 11 Z" className={styles.triangle} />}
            {item.shape === 'line' && <line x1="0" x2="14" y1="6" y2="6" className={styles.frontier} />}
            {item.shape === 'area' && <rect x="0" y="0" width="14" height="12" rx="2" className={styles.quadrantKey} />}
          </svg>
          {item.name}
        </span>
      ))}
    </div>
  )
}
