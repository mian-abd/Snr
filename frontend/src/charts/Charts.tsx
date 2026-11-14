import { useState } from 'react'
import styles from './charts.module.css'

/* ---------- Routing flow: one prompt fanning out to the models a preset picks ---------- */

export type FlowTarget = { id: string; name: string; share: number; detail?: string }

export function FlowDiagram({ targets, label }: { targets: FlowTarget[]; label: string }) {
  const width = 560
  const rowHeight = 46
  const shown = targets.slice(0, 6)
  const height = Math.max(200, shown.length * rowHeight + 40)
  const hub = { x: 190, y: height / 2 }
  const source = { x: 26, y: height / 2 }
  const top = (height - shown.length * rowHeight) / 2 + rowHeight / 2
  return (
    <div className={styles.frame}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}: ${shown.map((item) => `${item.name} ${Math.round(item.share * 100)}%`).join(', ')}`}>
        <path className={styles.flowPath} d={`M ${source.x + 8} ${source.y} L ${hub.x - 22} ${hub.y}`} strokeWidth={3} />
        {shown.map((target, index) => {
          const y = top + index * rowHeight
          const x = 330
          const stroke = 1.5 + target.share * 16
          return (
            <g key={target.id}>
              <path className={styles.flowPath} d={`M ${hub.x + 22} ${hub.y} C ${hub.x + 80} ${hub.y}, ${x - 80} ${y}, ${x - 10} ${y}`} strokeWidth={stroke} style={{ opacity: 0.25 + target.share * 0.65 }} />
              <circle className={styles.flowDot} cx={x - 4} cy={y} r={4} />
              <text className={styles.flowName} x={x + 8} y={y - 2}>{target.name}</text>
              <text className={styles.flowShare} x={x + 8} y={y + 14}>{`${Math.round(target.share * 100)}% of prompts${target.detail ? ` · ${target.detail}` : ''}`}</text>
            </g>
          )
        })}
        <circle className={styles.flowDot} cx={source.x} cy={source.y} r={7} />
        <text className={styles.flowMuted} x={source.x - 12} y={source.y + 28}>Prompt</text>
        <rect className={styles.flowHub} x={hub.x - 24} y={hub.y - 24} width={48} height={48} rx={14} />
        <text className={styles.flowHubText} x={hub.x} y={hub.y + 4} textAnchor="middle">AR</text>
        <text className={styles.flowMuted} x={hub.x} y={hub.y + 42} textAnchor="middle">Router</text>
        {targets.length > shown.length && (
          <text className={styles.flowMuted} x={330 + 8} y={height - 8}>{`+${targets.length - shown.length} more`}</text>
        )}
      </svg>
    </div>
  )
}

/* ---------- Horizontal bars ---------- */

export type BarDatum = { id: string; label: string; value: number; display: string; color?: string; title?: string }

export function BarList({ data, max, label }: { data: BarDatum[]; max?: number; label: string }) {
  const top = max ?? Math.max(...data.map((item) => item.value), 0) ?? 1
  return (
    <div className={styles.bars} role="list" aria-label={label}>
      {data.map((item) => (
        <div key={item.id} className={styles.barRow} role="listitem" title={item.title}>
          <span>{item.label}</span>
          <span className={styles.barTrack} aria-hidden="true">
            <span className={styles.barFill} style={{ width: `${top > 0 ? Math.max(1, (item.value / top) * 100) : 0}%`, background: item.color ?? 'var(--series-1)' }} />
          </span>
          <span className={styles.barValue}>{item.display}</span>
        </div>
      ))}
    </div>
  )
}

/** Two series per row (for example the same model on two prompt sets), with a legend. */
export function PairedBars({ rows, series, max }: {
  rows: Array<{ id: string; label: string; values: Array<number | null>; displays: string[] }>
  series: Array<{ name: string; color: string }>
  max: number
}) {
  return (
    <div>
      <div className={styles.legend} style={{ marginBottom: '0.75rem' }}>
        {series.map((item) => <span key={item.name}><i className={styles.swatch} style={{ background: item.color }} />{item.name}</span>)}
      </div>
      <div className={styles.bars}>
        {rows.map((row) => (
          <div key={row.id} className={styles.barRow}>
            <span>{row.label}</span>
            <span className={styles.barGroup}>
              {row.values.map((value, index) => (
                <span key={series[index].name} className={styles.barTrack} title={`${series[index].name}: ${row.displays[index]}`}>
                  {value != null && <span className={styles.barFill} style={{ width: `${Math.max(1, (value / max) * 100)}%`, background: series[index].color }} />}
                </span>
              ))}
            </span>
            <span className={styles.barValue}>{row.displays.join(' / ')}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ---------- A connected path of points (the user-priority sweep) ---------- */

export type PathPoint = { x: number; y: number; label?: string; detail: string[] }

export function PathChart({ title, subtitle, points, xLabel, yLabel, formatX, formatY }: {
  title: string
  subtitle?: string
  points: PathPoint[]
  xLabel: string
  yLabel: string
  formatX: (value: number) => string
  formatY: (value: number) => string
}) {
  const [active, setActive] = useState<number | null>(null)
  const width = 440
  const height = 260
  const margin = { top: 16, right: 18, bottom: 42, left: 48 }
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  const xMax = Math.max(...xs, 0) * 1.08 || 1
  const yMin = Math.floor((Math.min(...ys) - 0.02) * 50) / 50
  const yMax = Math.min(1, Math.ceil((Math.max(...ys) + 0.01) * 50) / 50)
  const sx = (value: number) => margin.left + (value / xMax) * (width - margin.left - margin.right)
  const sy = (value: number) => margin.top + (1 - (value - yMin) / (yMax - yMin || 1)) * (height - margin.top - margin.bottom)
  const yTicks = [yMin, (yMin + yMax) / 2, yMax]
  const xTicks = [0, xMax / 2, xMax]
  const current = active == null ? null : points[active]
  return (
    <figure className={styles.figure}>
      <figcaption><strong>{title}</strong>{subtitle && <span>{subtitle}</span>}</figcaption>
      <div className={styles.frame}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title}. The values are in the table.`}>
          {yTicks.map((tick) => (
            <g key={`y${tick}`}>
              <line className={styles.grid} x1={margin.left} x2={width - margin.right} y1={sy(tick)} y2={sy(tick)} />
              <text className={styles.tick} x={margin.left - 8} y={sy(tick) + 4} textAnchor="end">{formatY(tick)}</text>
            </g>
          ))}
          {xTicks.map((tick) => (
            <text key={`x${tick}`} className={styles.tick} x={sx(tick)} y={height - margin.bottom + 16} textAnchor="middle">{formatX(tick)}</text>
          ))}
          <line className={styles.axis} x1={margin.left} x2={width - margin.right} y1={height - margin.bottom} y2={height - margin.bottom} />
          <text className={styles.axisLabel} x={(margin.left + width - margin.right) / 2} y={height - 6} textAnchor="middle">{xLabel}</text>
          <text className={styles.axisLabel} transform={`translate(12 ${(margin.top + height - margin.bottom) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
          <path className={styles.line} d={points.map((point, index) => `${index ? 'L' : 'M'} ${sx(point.x)} ${sy(point.y)}`).join(' ')} />
          {points.map((point, index) => <circle key={index} className={styles.markLearned} cx={sx(point.x)} cy={sy(point.y)} r={4} />)}
          {points.map((point, index) => {
            if (!point.label) return null
            const right = sx(point.x) > (margin.left + width - margin.right) / 2
            return <text key={`l${index}`} className={styles.label} x={sx(point.x) + (right ? -8 : 8)} y={sy(point.y) - 9} textAnchor={right ? 'end' : 'start'}>{point.label}</text>
          })}
          {points.map((point, index) => (
            <circle key={`h${index}`} className={styles.hit} cx={sx(point.x)} cy={sy(point.y)} r={11} tabIndex={0} aria-label={point.detail.join(', ')}
              onPointerEnter={() => setActive(index)} onPointerLeave={() => setActive(null)} onFocus={() => setActive(index)} onBlur={() => setActive(null)} />
          ))}
        </svg>
        {current && (
          <div className={styles.tooltip} style={{ left: `${(sx(current.x) / width) * 100}%`, top: `${(sy(current.y) / height) * 100}%` }} role="status">
            <strong>{current.detail[0]}</strong>
            {current.detail.slice(1).map((line) => <span key={line}>{line}</span>)}
          </div>
        )}
      </div>
    </figure>
  )
}

/* ---------- An estimate with its interval, on a shared scale ---------- */

export function IntervalRow({ low, high, value, min, max, label }: { low: number; high: number; value: number; min: number; max: number; label: string }) {
  const at = (x: number) => `${((x - min) / (max - min || 1)) * 100}%`
  return (
    <div className={styles.interval} role="img" aria-label={label}>
      {min < 0 && max > 0 && <span className={styles.intervalZero} style={{ left: at(0) }} />}
      <span className={styles.intervalWhisker} style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})` }} />
      <span className={styles.intervalPoint} style={{ left: at(value) }} />
    </div>
  )
}

export function Legend({ items }: { items: Array<{ name: string; color: string; shape?: 'dot' | 'square' | 'triangle' }> }) {
  return (
    <div className={styles.legend}>
      {items.map((item) => (
        <span key={item.name}>
          {item.shape === 'triangle'
            ? <svg width="11" height="10" aria-hidden="true"><path d="M5.5 0 L11 10 L0 10 Z" fill={item.color} /></svg>
            : <i className={`${styles.swatch} ${item.shape === 'square' ? styles.swatchSquare : ''}`} style={{ background: item.color }} />}
          {item.name}
        </span>
      ))}
    </div>
  )
}
