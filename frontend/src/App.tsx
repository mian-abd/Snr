import { Menu, Moon, Search, Sun, Waypoints, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { CommandPalette } from './components/CommandPalette'
import { useCatalog, useHealth } from './lib/data'
import { shortTime } from './lib/format'
import { Link } from './lib/Link'
import { useRoute } from './lib/router'
import { useTheme } from './lib/theme'
import { Notice, Skeleton } from './ui'
import styles from './App.module.css'

// Each page loads its own code on first visit.
const ComparePage = lazy(() => import('./pages/ComparePage').then((m) => ({ default: m.ComparePage })))
const FaqPage = lazy(() => import('./pages/FaqPage').then((m) => ({ default: m.FaqPage })))
const HomePage = lazy(() => import('./pages/HomePage').then((m) => ({ default: m.HomePage })))
const LabPage = lazy(() => import('./pages/LabPage').then((m) => ({ default: m.LabPage })))
const ModelPage = lazy(() => import('./pages/ModelPage').then((m) => ({ default: m.ModelPage })))
const ModelsPage = lazy(() => import('./pages/ModelsPage').then((m) => ({ default: m.ModelsPage })))
const ResearchPage = lazy(() => import('./pages/ResearchPage').then((m) => ({ default: m.ResearchPage })))
const RouterPage = lazy(() => import('./pages/RouterPage').then((m) => ({ default: m.RouterPage })))

const links = [
  { to: '/router', label: 'Router' },
  { to: '/models', label: 'Models' },
  { to: '/compare', label: 'Compare' },
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

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent)
const searchKeys = isMac ? '⌘K' : 'Ctrl K'

function Page({ segments }: { segments: string[] }) {
  switch (segments[0]) {
    case undefined: return <HomePage />
    case 'router': return <RouterPage />
    case 'models': return segments[1] ? <ModelPage id={decodeURIComponent(segments[1])} /> : <ModelsPage />
    case 'compare': return <ComparePage />
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
  const [search, setSearch] = useState(false)
  const health = useHealth()
  useEffect(() => {
    setMenu(false)
    setSearch(false)
  }, [path])
  // Ctrl K (⌘K on a Mac) opens the search palette from anywhere, and closes it again.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearch((open) => !open)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 8)
    update()
    window.addEventListener('scroll', update, { passive: true })
    return () => window.removeEventListener('scroll', update)
  }, [])
  const current = (to: string) => (path === to || path.startsWith(`${to}/`) ? 'page' : undefined)

  return (
    <div className={styles.app}>
      <header className={`${styles.header} ${scrolled ? styles.headerScrolled : ''}`}>
        <div className={styles.headerInner}>
          <Link to="/" className={styles.brand}><Waypoints size={17} strokeWidth={2} />Adaptive Router</Link>
          <div className={styles.navWrap}>
            <nav className={styles.nav} aria-label="Main">
              {links.map((link) => <Link key={link.to} to={link.to} aria-current={current(link.to)}>{link.label}</Link>)}
            </nav>
          </div>
          <div className={styles.tools}>
            <button type="button" className={styles.search} onClick={() => setSearch(true)} aria-label="Search" aria-haspopup="dialog" aria-keyshortcuts={isMac ? 'Meta+K' : 'Control+K'} title={`Search pages, models, and research (${searchKeys})`}>
              <Search size={15} aria-hidden="true" />
              <span className={styles.searchLabel}>Search</span>
              <kbd className={styles.kbd} aria-hidden="true">{searchKeys}</kbd>
            </button>
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
          : <Suspense fallback={<div style={{ paddingTop: '3rem' }}><Skeleton height={420} /></div>}><Page segments={segments} /></Suspense>}
      </main>
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div>
            <span className={styles.footerBrand}>Adaptive LLM Router</span>
            <p>Open research on sending each prompt to the model that is good enough: measured outcomes, a small learned router, and every number reproducible from the published data. Prompts leave this computer only when you press Run.</p>
          </div>
          <div className={styles.footerCol}>
            <strong>Explore</strong>
            {links.map((link) => <Link key={link.to} to={link.to}>{link.label}</Link>)}
          </div>
          <div className={styles.footerCol}>
            <strong>Data</strong>
            <Link to="/research?section=downloads">Download the results</Link>
            <Link to="/research?section=method">Method and limits</Link>
            <Link to="/models">Live model catalog</Link>
          </div>
        </div>
      </footer>
      <CommandPalette open={search} onClose={() => setSearch(false)} />
    </div>
  )
}
