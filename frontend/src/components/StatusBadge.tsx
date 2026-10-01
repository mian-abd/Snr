import styles from './StatusBadge.module.css'

type Props = { status: string; label?: string }

export function StatusBadge({ status, label }: Props) {
  const normalized = status.toLowerCase()
  const tone = ['success', 'ok', 'completed', 'eligible'].includes(normalized)
    ? 'positive'
    : ['failed', 'error', 'provider_error', 'excluded'].includes(normalized)
      ? 'negative'
      : ['rate_limited', 'timeout'].includes(normalized)
        ? 'warning'
        : ['running', 'pending'].includes(normalized)
        ? 'active'
        : 'neutral'
  return (
    <span className={`${styles.badge} ${styles[tone]}`}>
      <span className={styles.dot} aria-hidden="true" />
      {label ?? status.replaceAll('_', ' ')}
    </span>
  )
}
