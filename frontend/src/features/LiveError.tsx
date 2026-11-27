import { isLimitNotice } from '../lib/publicMode'
import styles from './Panels.module.css'

/** A failed live call. A public-demo limit reads as a quiet notice; anything else is an error. */
export function LiveError({ error }: { error: Error }) {
  if (isLimitNotice(error)) return <p className={styles.notice} role="status">{error.message}</p>
  return <p className={styles.errorBox} role="alert">{error.message}</p>
}
