import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link } from '../lib/Link'
import { localLogo, makerOf } from '../lib/makers'
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

export function IconButton({ label, pressed, onClick, href, children }: { label: string; pressed?: boolean; onClick?: () => void; href?: string; children: ReactNode }) {
  if (href) return <a className={styles.iconButton} href={href} aria-label={label} title={label}>{children}</a>
  return <button type="button" className={styles.iconButton} aria-label={label} title={label} aria-pressed={pressed} onClick={onClick}>{children}</button>
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

export type Metric = 'accuracy' | 'cost' | 'speed' | 'route'

export function MetricKey({ metric }: { metric: Metric }) {
  return <i className={styles.metricKey} style={{ background: `var(--m-${metric})` }} aria-hidden="true" />
}

/** A chart in a card: serif title, a gray line on what it measures, tools, and footnotes. */
export function ChartCard({ id, metric, title, subtitle, tools, footnotes, children }: {
  id?: string
  metric?: Metric
  title: ReactNode
  subtitle?: ReactNode
  tools?: ReactNode
  footnotes?: Array<{ title: string; body: ReactNode }>
  children: ReactNode
}) {
  return (
    <section id={id} className={styles.chartCard} aria-label={typeof title === 'string' ? title : undefined}>
      <div className={styles.chartHead}>
        <div>
          <h3>{metric && <MetricKey metric={metric} />}{title}</h3>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {tools && <div className={styles.chartTools}>{tools}</div>}
      </div>
      <div className={styles.chartBody}>{children}</div>
      {footnotes && footnotes.length > 0 && (
        <div className={styles.footnotes}>
          {footnotes.map((note) => (
            <details key={note.title} className={styles.footnote}>
              <summary><Info size={13} />{note.title}</summary>
              <div>{note.body}</div>
            </details>
          ))}
        </div>
      )}
    </section>
  )
}

/** A short finding: a pill title, one or two sentences, and the logos of the models it names. */
export function Highlight({ title, value, children, models = [] }: { title: string; value?: string; children: ReactNode; models?: string[] }) {
  return (
    <div className={styles.highlight}>
      <div className={styles.highlightTitle}><span className={styles.pill}>{title}</span>{value && <span className={styles.highlightValue}>{value}</span>}</div>
      <p>{children}</p>
      {models.length > 0 && <div className={styles.highlightLogos}>{models.map((id) => <ModelLogo key={id} id={id} size={18} />)}</div>}
    </div>
  )
}

export function Highlights({ children, columns = 4 }: { children: ReactNode; columns?: number }) {
  return <div className={styles.highlights} style={{ ['--cols' as string]: columns }}>{children}</div>
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

/** The maker's logo for a model; local models show the runtime's mark. */
export function ModelLogo({ id, size = 20, framed = false, local = false }: { id: string; size?: number; framed?: boolean; local?: boolean }) {
  const maker = makerOf(id)
  const logo = local ? localLogo : maker.logo
  const mono = local || maker.mono
  if (!logo) {
    return <span className={`${styles.logo} ${styles.logoLetters}`} style={{ width: size, height: size, fontSize: size * 0.45 }} aria-hidden="true">{maker.name.slice(0, 1)}</span>
  }
  return (
    <span className={`${styles.logo} ${framed ? styles.logoFramed : ''} ${mono ? styles.mono : ''}`} style={{ width: size, height: size }} title={maker.name}>
      <img src={logo} alt="" width={size} height={size} />
    </span>
  )
}

/** Kept for older call sites: a framed maker logo. */
export function ModelAvatar({ model, size = 32 }: { model: { id: string; display_name: string }; size?: number }) {
  return <ModelLogo id={model.id} size={size} framed local={model.id.includes('local')} />
}

export function PageHeader({ eyebrow, title, description, actions, solo }: { eyebrow?: ReactNode; title: ReactNode; description?: ReactNode; actions?: ReactNode; solo?: boolean }) {
  return (
    <header className={`${styles.pageHeader} ${solo || !description ? styles.pageHeaderSolo : ''}`}>
      <div>
        {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
        <h1>{title}</h1>
        {solo && description && <p style={{ marginTop: '1rem' }}>{description}</p>}
        {actions && <div className={styles.headerActions}>{actions}</div>}
      </div>
      {!solo && description && <p>{description}</p>}
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

/** A sticky table of contents that marks the section in view. */
export function SideNav({ items, label = 'On this page', className }: { items: Array<{ id: string; label: string }>; label?: string; className?: string }) {
  const [active, setActive] = useState(items[0]?.id)
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (visible[0]) setActive(visible[0].target.id)
    }, { rootMargin: '-90px 0px -65% 0px' })
    items.forEach((item) => {
      const element = document.getElementById(item.id)
      if (element) observer.observe(element)
    })
    return () => observer.disconnect()
  }, [items])
  return (
    <nav className={`${styles.sideNav} ${className ?? ''}`} aria-label={label}>
      {items.map((item) => (
        <a key={item.id} href={`#${item.id}`} aria-current={active === item.id ? 'true' : undefined}
          onClick={(event) => { event.preventDefault(); setActive(item.id); document.getElementById(item.id)?.scrollIntoView({ behavior: 'smooth' }) }}>
          {item.label}
        </a>
      ))}
    </nav>
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
