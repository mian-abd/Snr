import { useState } from 'react'
import base from './charts.module.css'
import styles from './explorers.module.css'
import { thinTicks, useWidth, type Scale } from './scales'

export type DumbbellRow = {
  id: string
  label: string
  /** A short tag beside the label, such as "Really happened". */
  flag?: string
  /** The filled circle (for example the router told about the change). */
  a: number
  /** The hollow square (for example the router with its old estimates). */
  b: number
  /** The difference a minus b, already worded; the sign carries the direction, the tone only repeats it. */
  delta: { text: string; tone: 'good' | 'bad' | 'plain' | 'same' }
  /** Tooltip lines: the first is the title. */
  details: string[]
  /** What a screen reader hears for the row. */
  summary: string
}

const clamp = (value: number) => Math.max(0, Math.min(1, value))
const at = (scale: Scale, value: number) => `${clamp(scale.at(value)) * 100}%`

/**
 * One row per item, two marks per row joined by a line: a filled circle and a hollow square,
 * so the two series differ in shape as well as in color. Where they coincide, the circle sits
 * inside the square. Rows are focusable; hover or focus shows both numbers.
 */
export function Dumbbell({ rows, series, scale, axisLabel, deltaLabel, label }: {
  rows: DumbbellRow[]
  series: [string, string]
  scale: Scale
  axisLabel: string
  deltaLabel: string
  label: string
}) {
  const [active, setActive] = useState<string | null>(null)
  const [axisRef, axisWidth] = useWidth<HTMLSpanElement>(600)
  const labels = thinTicks(scale.ticks, (value) => clamp(scale.at(value)) * axisWidth, 6)
  return (
    <div className={styles.dumbbell}>
      <div className={styles.dbLegend}>
        <span><i className={styles.keyA} aria-hidden="true" />{series[0]}</span>
        <span><i className={styles.keyB} aria-hidden="true" />{series[1]}</span>
      </div>
      <div className={`${styles.dbRow} ${styles.dbHead}`} aria-hidden="true">
        <span>Change</span><span /><span>{deltaLabel}</span>
      </div>
      <div role="list" aria-label={label} className={styles.dbList}>
        {rows.map((row, index) => {
          const left = Math.min(clamp(scale.at(row.a)), clamp(scale.at(row.b)))
          const right = Math.max(clamp(scale.at(row.a)), clamp(scale.at(row.b)))
          const show = () => setActive(row.id)
          const hide = () => setActive((current) => (current === row.id ? null : current))
          return (
            <div key={row.id} role="listitem" tabIndex={0} aria-label={row.summary} className={`${styles.dbRow} ${row.flag ? styles.dbFlagged : ''}`}
              onPointerEnter={show} onPointerLeave={hide} onFocus={show} onBlur={hide}>
              <span className={styles.dbLabel}>
                <span>{row.label}</span>
                {row.flag && <em className={styles.dbFlag}>{row.flag}</em>}
              </span>
              <span className={styles.dbTrack} aria-hidden="true">
                {scale.ticks.map((tick) => <i key={tick.value} className={styles.dbGrid} style={{ left: at(scale, tick.value) }} />)}
                <span className={styles.dbLine} style={{ left: `${left * 100}%`, width: `${(right - left) * 100}%` }} />
                <span className={styles.dbB} style={{ left: at(scale, row.b) }} />
                <span className={styles.dbA} style={{ left: at(scale, row.a) }} />
                {active === row.id && (
                  <span className={`${base.tooltip} ${styles.dbTip} ${index < 2 ? styles.tipBelow : ''}`} style={{ left: `clamp(6rem, ${((left + right) / 2) * 100}%, calc(100% - 6rem))` }}>
                    <strong>{row.details[0]}</strong>
                    {row.details.slice(1).map((line) => <span key={line}>{line}</span>)}
                  </span>
                )}
              </span>
              <span className={`${styles.dbDelta} ${styles[row.delta.tone]}`}>{row.delta.text}</span>
            </div>
          )
        })}
      </div>
      <div className={`${styles.dbRow} ${styles.dbAxis}`} aria-hidden="true">
        <span />
        <span ref={axisRef} className={styles.dbTicks}>
          {labels.map((tick) => <span key={tick.value} style={{ left: at(scale, tick.value) }}>{tick.label}</span>)}
        </span>
        <span />
      </div>
      <p className={styles.dbAxisLabel}>{axisLabel}</p>
    </div>
  )
}
