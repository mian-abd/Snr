import { useState, type KeyboardEvent, type MouseEvent, type PointerEvent } from 'react'
import base from './charts.module.css'
import styles from './explorers.module.css'
import { thinTicks, useWidth, type Scale } from './scales'

export type SweepPoint = { weight: number; x: number; y: number; details: string[] }

type Group = { key: string; indices: number[]; x: number; y: number; name: string }
type Box = [number, number, number, number]

const MARGIN = { top: 26, right: 22, bottom: 46, left: 50 }
const CHAR = 6.3
/** Where a name may sit relative to its mark, best first. */
const SPOTS: Array<[number, number, 'start' | 'end' | 'middle']> = [
  [12, -10, 'start'], [-12, -10, 'end'], [12, 18, 'start'], [-12, 18, 'end'], [0, -16, 'middle'], [0, 26, 'middle'],
  [14, 4, 'start'], [-14, 4, 'end'],
]

/** Settings that landed on the same result share one mark, named by their weights. */
function groupsOf(points: SweepPoint[], weightName: string): Group[] {
  const groups = new Map<string, Group>()
  points.forEach((point, index) => {
    const key = `${point.x.toPrecision(6)}|${point.y.toPrecision(6)}`
    const group = groups.get(key) ?? { key, indices: [], x: point.x, y: point.y, name: '' }
    group.indices.push(index)
    groups.set(key, group)
  })
  for (const group of groups.values()) {
    const weights = group.indices.map((index) => points[index].weight)
    const runs = group.indices.every((index, i) => i === 0 || index === group.indices[i - 1] + 1)
    group.name = `${weightName} ${weights.length > 1 && runs ? `${weights[0]}–${weights[weights.length - 1]}` : weights.join(', ')}`
  }
  return [...groups.values()]
}

/**
 * A path of settings: accuracy up the side, cost or time along the bottom, one mark per
 * distinct result in the order the weight rises. The picked setting gets a ring and guide
 * lines to both axes; clicking a mark (or Enter on it) picks it.
 */
export function SweepChart({ points, selected, onSelect, xScale, yScale, xLabel, yLabel, weightName, label }: {
  points: SweepPoint[]
  selected: number
  onSelect: (index: number) => void
  xScale: Scale
  yScale: Scale
  xLabel: string
  yLabel: string
  weightName: string
  label: string
}) {
  const [ref, width] = useWidth<HTMLDivElement>(640)
  const [active, setActive] = useState<string | null>(null)
  const height = width < 480 ? 280 : 320
  const plot = { x0: MARGIN.left, y0: MARGIN.top, x1: Math.max(MARGIN.left + 40, width - MARGIN.right), y1: height - MARGIN.bottom }
  const sx = (value: number) => plot.x0 + Math.max(0, Math.min(1, xScale.at(value))) * (plot.x1 - plot.x0)
  const sy = (value: number) => plot.y0 + (1 - Math.max(0, Math.min(1, yScale.at(value)))) * (plot.y1 - plot.y0)
  const groups = groupsOf(points, weightName)
  const picked = groups.find((group) => group.indices.includes(selected))
  const current = groups.find((group) => group.key === active)

  // Name the picked setting first, then the two ends: each name takes the spot near its mark
  // that crosses the least of the path, and a name that would land on another is dropped.
  const trail: Array<[number, number]> = points.flatMap((point, index) => {
    if (!index) return [[sx(point.x), sy(point.y)] as [number, number]]
    const from = points[index - 1]
    return Array.from({ length: 12 }, (_, step) => {
      const t = (step + 1) / 12
      return [sx(from.x + (point.x - from.x) * t), sy(from.y + (point.y - from.y) * t)] as [number, number]
    })
  })
  const named: Array<{ key: string; text: string; x: number; y: number; anchor: 'start' | 'end' | 'middle'; strong: boolean }> = []
  const boxes: Box[] = []
  const ordered = [picked, groups[0], groups[groups.length - 1]].filter((group, index, all): group is Group => !!group && all.indexOf(group) === index)
  for (const group of ordered) {
    const px = sx(group.x)
    const py = sy(group.y)
    const text = group === picked ? group.name : group.name.replace(`${weightName} `, 'weight ')
    const w = text.length * CHAR
    let best: { cost: number; x: number; y: number; anchor: 'start' | 'end' | 'middle'; box: Box } | null = null
    for (const [dx, dy, anchor] of SPOTS) {
      const x = px + dx
      const y = py + dy
      const left = anchor === 'start' ? x : anchor === 'end' ? x - w : x - w / 2
      const box: Box = [left, y - 11, left + w, y + 3]
      const outside = box[0] < plot.x0 - 6 || box[2] > plot.x1 + 6 || box[1] < plot.y0 - 18 || box[3] > plot.y1 - 2
      const crowded = boxes.some((other) => box[0] < other[2] && other[0] < box[2] && box[1] < other[3] && other[1] < box[3])
      const crossed = trail.filter(([tx, ty]) => tx > box[0] - 2 && tx < box[2] + 2 && ty > box[1] - 2 && ty < box[3] + 2).length
      const cost = (outside ? 100 : 0) + (crowded ? 60 : 0) + crossed
      if (!best || cost < best.cost) best = { cost, x, y, anchor, box }
    }
    if (!best || (best.cost >= 60 && group !== picked)) continue
    boxes.push(best.box)
    named.push({ key: group.key, text, x: best.x, y: best.y, anchor: best.anchor, strong: group === picked })
  }
  // Free and a tenth of a cent sit close together on a narrow screen.
  const xTicks = thinTicks(xScale.ticks, sx, CHAR)

  const choose = (group: Group) => onSelect(group.indices.includes(selected) ? selected : group.indices[0])
  const onKey = (event: KeyboardEvent, group: Group) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    choose(group)
  }
  // The pointer goes to the nearest mark, so marks a few pixels apart can both be reached.
  const nearest = (event: PointerEvent<SVGRectElement> | MouseEvent<SVGRectElement>) => {
    const box = event.currentTarget.ownerSVGElement?.getBoundingClientRect()
    if (!box) return null
    const x = event.clientX - box.left
    const y = event.clientY - box.top
    let best: Group | null = null
    let reach = 26
    for (const group of groups) {
      const distance = Math.hypot(sx(group.x) - x, sy(group.y) - y)
      if (distance < reach) [best, reach] = [group, distance]
    }
    return best
  }

  return (
    <div ref={ref} className={styles.sweepFrame}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" aria-label={label}>
        {yScale.ticks.map((tick) => (
          <g key={`y${tick.value}`}>
            <line className={base.grid} x1={plot.x0} x2={plot.x1} y1={sy(tick.value)} y2={sy(tick.value)} />
            <text className={base.tick} x={plot.x0 - 8} y={sy(tick.value) + 4} textAnchor="end">{tick.label}</text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <text key={`x${tick.value}`} className={base.tick} x={sx(tick.value)} y={plot.y1 + 18} textAnchor="middle">{tick.label}</text>
        ))}
        <line className={base.axis} x1={plot.x0} x2={plot.x1} y1={plot.y1} y2={plot.y1} />
        <text className={base.axisLabel} x={(plot.x0 + plot.x1) / 2} y={height - 6} textAnchor="middle">{xLabel}</text>
        <text className={base.axisLabel} transform={`translate(13 ${(plot.y0 + plot.y1) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
        {picked && (
          <g className={styles.sweepGuide}>
            <line x1={sx(picked.x)} x2={sx(picked.x)} y1={sy(picked.y)} y2={plot.y1} />
            <line x1={plot.x0} x2={sx(picked.x)} y1={sy(picked.y)} y2={sy(picked.y)} />
          </g>
        )}
        <path className={styles.sweepPath} d={points.map((point, index) => `${index ? 'L' : 'M'} ${sx(point.x)} ${sy(point.y)}`).join(' ')} />
        {groups.map((group) => <circle key={group.key} className={styles.sweepDot} cx={sx(group.x)} cy={sy(group.y)} r={4.5} />)}
        {picked && <circle className={styles.sweepRing} cx={sx(picked.x)} cy={sy(picked.y)} r={9.5} />}
        {named.map((item) => <text key={`n${item.key}`} className={item.strong ? base.labelStrong : base.label} x={item.x} y={item.y} textAnchor={item.anchor}>{item.text}</text>)}
        <rect className={styles.sweepHit} x={plot.x0 - 16} y={plot.y0 - 16} width={plot.x1 - plot.x0 + 32} height={plot.y1 - plot.y0 + 24}
          style={{ cursor: current ? 'pointer' : 'default' }} aria-hidden="true"
          onPointerMove={(event) => setActive(nearest(event)?.key ?? null)} onPointerLeave={() => setActive(null)}
          onClick={(event) => { const group = nearest(event); if (group) choose(group) }} />
        {groups.map((group) => (
          <circle key={`hit${group.key}`} className={`${base.hit} ${styles.sweepKey}`} cx={sx(group.x)} cy={sy(group.y)} r={13} tabIndex={0} role="button"
            aria-pressed={group === picked} aria-label={[group.name, ...points[group.indices[0]].details].join(', ')}
            onClick={() => choose(group)} onKeyDown={(event) => onKey(event, group)} onFocus={() => setActive(group.key)} onBlur={() => setActive(null)} />
        ))}
      </svg>
      {current && (
        <div className={base.tooltip} style={{ left: Math.max(96, Math.min(width - 96, sx(current.x))), top: sy(current.y) }}>
          <strong>{current.name}</strong>
          {points[current.indices[0]].details.map((line) => <span key={line}>{line}</span>)}
          <span className={styles.tipHint}>{current === picked ? 'Picked' : 'Click to pick'}</span>
        </div>
      )}
    </div>
  )
}
