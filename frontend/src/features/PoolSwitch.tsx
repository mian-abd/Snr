import type { RoutingPool } from '../api/types'
import styles from './Panels.module.css'
import { poolLabels } from './pools'

type Props = {
  value: RoutingPool
  onChange: (pool: RoutingPool) => void
  descriptions: Record<RoutingPool, string>
}

export function PoolSwitch({ value, onChange, descriptions }: Props) {
  return (
    <fieldset className={styles.priorityFieldset}>
      <legend>Model pool</legend>
      <div className={styles.poolGrid}>
        {(['paid', 'baseline'] as const).map((pool) => (
          <button key={pool} type="button" aria-pressed={value === pool} className={value === pool ? styles.priorityActive : styles.priorityOption} onClick={() => onChange(pool)}>
            <strong>{poolLabels[pool]}</strong><span>{descriptions[pool]}</span>
          </button>
        ))}
      </div>
    </fieldset>
  )
}
