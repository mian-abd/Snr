import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { avatarFor } from '../lib/data'
import { Link } from '../lib/Link'
import styles from './ui.module.css'


type Variant = 'primary' | 'secondary' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

const buttonClass = (variant: Variant, size: Size, extra?: string) =>
  [styles.button, styles[variant], size !== 'md' ? styles[size] : '', extra ?? ''].join(' ')

export function Button({ variant = 'secondary', size = 'md', className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return <button type="button" className={buttonClass(variant, size, className)} {...props} />
}

export function ButtonLink({ to, variant = 'secondary', size = 'md', children }: { to: string; variant?: Variant; size?: Size; children: ReactNode }) {
  return <Link to={to} className={buttonClass(variant, size)}>{children}</Link>
}

type Tone = 'neutral' | 'accent' | 'good' | 'warn' | 'bad'

export function Badge({ tone = 'neutral', dot, children, title }: { tone?: Tone; dot?: boolean; children: ReactNode; title?: string }) {
  return <span className={`${styles.badge} ${tone !== 'neutral' ? styles[tone] : ''}`} title={title}>{dot && <i aria-hidden="true" />}{children}</span>
}

export function Card({ children, className, pad = true, id }: { children: ReactNode; className?: string; pad?: boolean; id?: string }) {
  return <div id={id} className={`${styles.card} ${pad ? styles.cardPad : ''} ${className ?? ''}`}>{children}</div>
}

export function CardHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className={styles.cardHeader}>
      <div><h3>{title}</h3>{description && <p>{description}</p>}</div>
      {actions}
    </div>
  )
}

export function Stat({ label, value, hint, was }: { label: string; value: ReactNode; hint?: ReactNode; was?: ReactNode }) {
  return (
    <div className={styles.stat}>
      <span>{label}</span>
      <strong>{was && <span className={styles.statStrike}>{was}</span>}<span className={was ? styles.statNew : undefined}>{value}</span></strong>
      {hint && <small>{hint}</small>}
    </div>
  )
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: Array<{ id: T; label: ReactNode; title?: string }>
  value: T
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div className={styles.segmented} role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.id} type="button" aria-pressed={option.id === value} title={option.title} onClick={() => onChange(option.id)}>{option.label}</button>
      ))}
    </div>
  )
}

export function ModelAvatar({ model, size = 32 }: { model: { id: string; display_name: string }; size?: number }) {
  const { tint, letters } = avatarFor(model)
  return <span className={styles.avatar} style={{ width: size, height: size, background: tint, fontSize: size * 0.4 }} aria-hidden="true">{letters}</span>
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: ReactNode; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className={styles.pageHeader}>
      <div>
        {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions}
    </header>
  )
}

export function Section({ id, icon, title, description, actions, children }: { id?: string; icon?: ReactNode; title: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className={styles.section} aria-labelledby={id ? `${id}-title` : undefined}>
      <div className={styles.sectionTitle}>
        <div><h2 id={id ? `${id}-title` : undefined}>{icon}{title}</h2>{description && <p>{description}</p>}</div>
        {actions}
      </div>
      {children}
    </section>
  )
}

const noticeIcons = { info: Info, warn: AlertTriangle, good: CheckCircle2, bad: XCircle }
const noticeClass = { info: styles.noticeInfo, warn: styles.noticeWarn, good: styles.noticeGood, bad: styles.noticeBad }

export function Notice({ tone = 'info', children, role, icon }: { tone?: keyof typeof noticeIcons; children: ReactNode; role?: string; icon?: ReactNode }) {
  const Icon = noticeIcons[tone]
  return <div className={`${styles.notice} ${noticeClass[tone]}`} role={role}>{icon ?? <Icon size={16} />}<div>{children}</div></div>
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: ReactNode; children?: ReactNode }) {
  return <div className={styles.empty}>{icon}<strong>{title}</strong>{children && <span>{children}</span>}</div>
}

export function Skeleton({ height = 120 }: { height?: number }) {
  return <div className={styles.skeleton} style={{ height }} aria-hidden="true" />
}

export function Meter({ value, color, label }: { value: number; color?: string; label?: string }) {
  return (
    <div className={styles.meter} role="img" aria-label={label}>
      <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: color }} />
    </div>
  )
}
