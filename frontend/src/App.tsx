import { Menu, Moon, Route as RouteIcon, Sun, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useCatalog, useHealth } from './lib/data'
import { shortTime } from './lib/format'
import { Link } from './lib/Link'
import { useRoute } from './lib/router'
import { useTheme } from './lib/theme'
import { FaqPage } from './pages/FaqPage'
import { HomePage } from './pages/HomePage'
import { LabPage } from './pages/LabPage'
import { ModelPage } from './pages/ModelPage'
import { ModelsPage } from './pages/ModelsPage'
import { ResearchPage } from './pages/ResearchPage'
import { RouterPage } from './pages/RouterPage'
import { Notice } from './ui'
import styles from './App.module.css'

const links = [
  { to: '/router', label: 'Router' },
  { to: '/models', label: 'Models' },
  { to: '/research', label: 'Research' },
  { to: '/faq', label: 'FAQ' },
  { to: '/lab', label: 'Lab' },
]

function CatalogPill() {
  const catalog = useCatalog()
  const status = catalog.data
  if (!status) return null
  const gone = status.models.filter((item) => !item.available).length
  const tone = status.source !== 'live' ? 'off' : gone ? 'warn' : 'good'
  const text = status.source === 'live'
    ? gone ? `${gone} model unavailable` : 'All models available'
    : status.source === 'snapshot' ? 'Live check failed' : 'Live check off'
  return (
    <Link to="/models" className={styles.status} data-tone={tone} title={`Provider catalogs checked ${shortTime(status.checked_at_utc)}`}>
      <i aria-hidden="true" /><span>{text}</span>
    </Link>
  )
}

function Page({ segments }: { segments: string[] }) {
  switch (segments[0]) {
    case undefined: return <HomePage />
    case 'router': return <RouterPage />
    case 'models': return segments[1] ? <ModelPage id={decodeURIComponent(segments[1])} /> : <ModelsPage />
    case 'research': return <ResearchPage />
    case 'faq': return <FaqPage />
    case 'lab': return <LabPage />
    default: return <HomePage />
  }
}

export default function App() {
  const { segments, path } = useRoute()
  const { theme, toggle } = useTheme()
  const [menu, setMenu] = useState(false)
  const health = useHealth()
  useEffect(() => setMenu(false), [path])
  const current = (to: string) => (path === to || path.startsWith(`${to}/`) ? 'page' : undefined)

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link to="/" className={styles.brand}><span className={styles.mark}><RouteIcon size={15} strokeWidth={2.4} /></span>Adaptive Router</Link>
          <nav className={styles.nav} aria-label="Main">
            {links.map((link) => <Link key={link.to} to={link.to} aria-current={current(link.to)}>{link.label}</Link>)}
          </nav>
          <span className={styles.spacer} />
          <div className={styles.tools}>
            <CatalogPill />
            <button type="button" className={styles.iconButton} onClick={toggle} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} title={theme === 'dark' ? 'Light theme' : 'Dark theme'}>
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button type="button" className={`${styles.iconButton} ${styles.menuButton}`} onClick={() => setMenu(!menu)} aria-label="Menu" aria-expanded={menu}>
              {menu ? <X size={16} /> : <Menu size={16} />}
            </button>
          </div>
        </div>
        {menu && (
          <nav className={styles.mobileNav} aria-label="Main">
            {links.map((link) => <Link key={link.to} to={link.to} aria-current={current(link.to)}>{link.label}</Link>)}
          </nav>
        )}
      </header>
      <main className={styles.main}>
        {health.isError
          ? <div className={styles.error}><Notice tone="bad" role="alert"><strong>The server could not be reached.</strong> Start it with <code>./scripts/demo.ps1</code> and reload this page.</Notice></div>
          : <Page segments={segments} />}
      </main>
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div>
            <strong>Adaptive LLM Router</strong>
            <p>Open research on sending each prompt to the model that is good enough: measured outcomes, a small learned router, and every number reproducible from the published data. Prompts leave this computer only when you press Run.</p>
          </div>
          <div className={styles.footerLinks}>
            {links.map((link) => <Link key={link.to} to={link.to}>{link.label}</Link>)}
            <Link to="/research?section=downloads">Download the data</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
