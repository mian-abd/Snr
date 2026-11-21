import { useState } from 'react'
import base from './charts.module.css'
import styles from './explorers.module.css'

export type ScoreTerms = { quality: number; cost: number; time: number; failures: number; score: number }

/** The penalties, in the order they are taken off the right end of the quality term. */
const penalties = [
  { key: 'cost', name: 'Cost', legend: 'Cost penalty', color: 'var(--m-cost)' },
  { key: 'time', name: 'Time', legend: 'Time penalty', color: 'var(--m-speed)' },
  { key: 'failures', name: 'Failures', legend: 'Failure penalty', color: 'var(--bad)' },
] as const

const fixed = (value: number) => value.toFixed(3)

function scoreSentence(name: string, terms: ScoreTerms) {
  return `${name}: chance right ${fixed(terms.quality)}, minus cost ${fixed(terms.cost)}, time ${fixed(terms.time)}, and failures ${fixed(terms.failures)}, scores ${terms.score.toFixed(2)}`
}

/**
 * A score as a bar: the full length is the quality term (the chance it's right, times its
 * weight), and the cost, time, and failure penalties are cut off its right end in their own
 * colors, so the ink that is left is the score. `low` and `high` give every row the same scale;
 * a negative score pushes the penalties past the zero line.
 */
export function ScoreBar({ name, terms, low, high }: { name: string; terms: ScoreTerms; low: number; high: number }) {
  const [open, setOpen] = useState(false)
  const span = high - low || 1
  const at = (value: number) => ((Math.max(low, Math.min(high, value)) - low) / span) * 100
  let edge = terms.quality
  const cuts = penalties.map((item) => {
    const size = terms[item.key]
    const segment = { ...item, size, from: at(edge - size), to: at(edge) }
    edge -= size
    return segment
  })
  return (
    <span className={styles.scoreBar} role="img" tabIndex={0} aria-label={scoreSentence(name, terms)}
      onPointerEnter={() => setOpen(true)} onPointerLeave={() => setOpen(false)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
      <span className={styles.scoreTrack}>
        {low < 0 && <i className={styles.scoreZero} style={{ left: `${at(0)}%` }} />}
        {terms.score > 0 && <span className={styles.scoreInk} style={{ left: `${at(0)}%`, width: `${at(terms.score) - at(0)}%` }} />}
        {cuts.filter((cut) => cut.size > 0).map((cut) => (
          <span key={cut.key} className={styles.scoreCut} style={{ left: `${cut.from}%`, width: `max(3px, ${cut.to - cut.from}%)`, background: cut.color }} />
        ))}
      </span>
      {open && (
        <span className={`${base.tooltip} ${styles.scoreTip}`} style={{ left: `clamp(6rem, ${at(terms.quality)}%, calc(100% - 6rem))` }}>
          <strong>{name}</strong>
          <span className={styles.tipRow}><i style={{ background: 'var(--ink)' }} />Chance right<b>{fixed(terms.quality)}</b></span>
          {penalties.map((item) => (
            <span key={item.key} className={styles.tipRow}><i style={{ background: item.color }} />− {item.name.toLowerCase()}<b>{fixed(terms[item.key])}</b></span>
          ))}
          <span className={`${styles.tipRow} ${styles.tipTotal}`}><i aria-hidden="true" />= Score<b>{terms.score.toFixed(3)}</b></span>
        </span>
      )}
    </span>
  )
}

/** The key for the score bars: what the ink and each colored piece stand for. */
export function ScoreLegend() {
  return (
    <div className={styles.scoreLegend}>
      <span><i style={{ background: 'var(--ink)' }} />Score</span>
      {penalties.map((item) => <span key={item.key}><i style={{ background: item.color }} />{item.legend}</span>)}
      <small>The whole bar is the chance it's right; the colored pieces are taken off it.</small>
    </div>
  )
}
