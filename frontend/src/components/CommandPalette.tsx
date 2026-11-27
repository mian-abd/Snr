import { BookOpen, CircleHelp, Columns3, CornerDownLeft, FlaskConical, Hash, House, MessageSquareText, Rows3, Search, Waypoints } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { accessLabel, addedLabel, modelViews, useFinalReport, useLearnedReport, usePool, useScoringFix, useStudyReports } from '../lib/data'
import { makerOf } from '../lib/makers'
import { freshShare, plainName } from '../lib/measures'
import { navigate } from '../lib/router'
import { rankScore, researchSections, sitePages } from '../lib/search'
import { ModelLogo } from '../ui'
import { MatchText } from './MatchText'
import options from './options.module.css'
import styles from './CommandPalette.module.css'

type GroupId = 'pages' | 'models' | 'research'
type Item = {
  key: string
  group: GroupId
  title: string
  sub: string
  keywords: string
  path: string
  icon: ReactNode
  /** Fresh-prompt accuracy, for models. */
  score?: number | null
}

const groupTitle: Record<GroupId, string> = { pages: 'Pages', models: 'Models', research: 'Research sections' }
const pageIcons: Record<string, ReactNode> = {
  '/': <House size={16} />,
  '/router': <Waypoints size={16} />,
  '/models': <Rows3 size={16} />,
  '/compare': <Columns3 size={16} />,
  '/research': <BookOpen size={16} />,
  '/prompts': <MessageSquareText size={16} />,
  '/faq': <CircleHelp size={16} />,
  '/lab': <FlaskConical size={16} />,
}

/** Focusable controls inside an element, in tab order. */
const focusables = (root: HTMLElement) =>
  [...root.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter((element) => !element.hasAttribute('disabled'))

/** The search palette: pages, models, and research sections, opened with Ctrl K or ⌘K. */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null
  return createPortal(<Palette onClose={onClose} />, document.body)
}

function Palette({ onClose }: { onClose: () => void }) {
  const pool = usePool()
  const learned = useLearnedReport()
  const final = useFinalReport()
  const studies = useStudyReports()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  const optionId = (index: number) => `${listId}-option-${index}`

  const studyIds = studies.map((study) => study.study_id).join(',')
  const hasScoringFix = Boolean(useScoringFix().data)
  const items = useMemo<Item[]>(() => {
    const pages: Item[] = sitePages.map((page) => ({ key: `page:${page.path}`, group: 'pages', title: page.label, sub: page.about, keywords: page.keywords, path: page.path, icon: pageIcons[page.path] }))
    const views = modelViews(pool.data, null, learned.data, final.data, studies)
      .map((view) => ({ view, score: freshShare(view) }))
      .sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
    const models: Item[] = views.map(({ view, score }) => {
      const maker = makerOf(view.id)
      const added = view.added ? ` · ${addedLabel[view.added] ?? 'Added'}` : ''
      return {
        key: `model:${view.id}`,
        group: 'models',
        title: plainName(view.pool.display_name),
        sub: `${maker.name} · ${accessLabel[view.pool.access] ?? view.pool.access}${added}`,
        keywords: `${view.id} ${view.pool.family} ${view.pool.access} ${view.added ?? ''}`,
        path: `/models/${encodeURIComponent(view.id)}`,
        icon: <ModelLogo id={view.id} size={18} local={view.pool.access === 'local'} />,
        score,
      }
    })
    const present = new Set(studyIds.split(',').filter(Boolean).map((id) => `study-${id}`))
    if (hasScoringFix) present.add('scoring-fix')
    const research: Item[] = researchSections
      .filter((section) => !(section.id.startsWith('study-') || section.id === 'scoring-fix') || present.has(section.id))
      .map((section) => ({ key: `research:${section.id}`, group: 'research', title: section.label, sub: 'Research', keywords: section.keywords, path: `/research?section=${section.id}`, icon: <Hash size={16} /> }))
    return [...pages, ...models, ...research]
    // The study reports are a new array each render; their IDs say when they changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pool.data, learned.data, final.data, studyIds, hasScoringFix])

  const groups = useMemo(() => {
    const order: GroupId[] = ['pages', 'models', 'research']
    const ranked = items
      .map((item) => ({ item, rank: query.trim() ? rankScore(query, item.title, item.keywords, item.sub) : 0 }))
      .filter((entry): entry is { item: Item; rank: number } => entry.rank != null)
    return order
      .map((id) => {
        const entries = ranked.filter((entry) => entry.item.group === id).sort((a, b) => b.rank - a.rank)
        return { id, items: entries.map((entry) => entry.item), best: entries[0]?.rank ?? -1 }
      })
      .filter((group) => group.items.length > 0)
      .sort((a, b) => (query.trim() ? b.best - a.best : 0))
  }, [items, query])
  const flat = groups.flatMap((group) => group.items)
  const current = flat.length ? Math.min(active, flat.length - 1) : -1

  // Opening: focus the box, keep the page behind out of reach, and give focus back on close.
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const root = document.getElementById('root')
    root?.setAttribute('inert', '')
    const body = document.body.style
    const saved = { overflow: body.overflow, paddingRight: body.paddingRight }
    const scrollbar = window.innerWidth - document.documentElement.clientWidth
    body.overflow = 'hidden'
    if (scrollbar > 0) body.paddingRight = `${scrollbar}px`
    inputRef.current?.focus()
    return () => {
      root?.removeAttribute('inert')
      body.overflow = saved.overflow
      body.paddingRight = saved.paddingRight
      previous?.focus()
    }
  }, [])

  useEffect(() => {
    if (current >= 0) document.getElementById(optionId(current))?.scrollIntoView?.({ block: 'nearest' })
    // optionId only depends on the stable list ID.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current])

  const choose = (item: Item | undefined) => {
    if (!item) return
    onClose()
    navigate(item.path)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!flat.length) return
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((current + step + flat.length) % flat.length)
    } else if ((event.key === 'Home' || event.key === 'End') && event.ctrlKey && flat.length) {
      event.preventDefault()
      setActive(event.key === 'Home' ? 0 : flat.length - 1)
    } else if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
      event.preventDefault()
      choose(flat[current])
    } else if (event.key === 'Tab' && dialogRef.current) {
      // Keep focus inside the dialog.
      const controls = focusables(dialogRef.current)
      if (!controls.length) return
      const index = controls.indexOf(document.activeElement as HTMLElement)
      const next = event.shiftKey ? (index <= 0 ? controls.length - 1 : index - 1) : (index + 1) % controls.length
      event.preventDefault()
      controls[next].focus()
    }
  }

  let index = -1
  const loadingModels = pool.isLoading
  return (
    <div className={styles.backdrop} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div ref={dialogRef} className={styles.dialog} role="dialog" aria-modal="true" aria-label="Search the site" onKeyDown={onKeyDown}>
        <div className={styles.searchRow}>
          <Search size={18} aria-hidden="true" className={styles.searchIcon} />
          <input
            ref={inputRef}
            className={styles.input}
            type="text"
            role="combobox"
            aria-label="Search pages, models, and research sections"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={current >= 0 ? optionId(current) : undefined}
            placeholder="Search pages, models, research…"
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(event) => { setQuery(event.target.value); setActive(0) }}
          />
          <button type="button" className={styles.close} onClick={onClose} aria-label="Close search">Esc</button>
        </div>
        <div className={styles.results}>
          <ul id={listId} role="listbox" aria-label="Results" className={options.list}>
            {groups.map((group) => (
              <li key={group.id} role="presentation" className={options.group}>
                <div id={`${listId}-${group.id}`} className={options.groupTitle} aria-hidden="true">{groupTitle[group.id]}</div>
                <ul role="group" aria-labelledby={`${listId}-${group.id}`} className={options.list}>
                  {group.items.map((item) => {
                    index += 1
                    const position = index
                    const selected = position === current
                    return (
                      <li
                        key={item.key}
                        id={optionId(position)}
                        role="option"
                        aria-selected={selected}
                        className={options.option}
                        onMouseMove={() => { if (!selected) setActive(position) }}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => choose(item)}
                      >
                        <span className={options.icon} aria-hidden="true">{item.icon}</span>
                        <span className={options.text}>
                          <span className={options.title}><MatchText text={item.title} query={query} /></span>
                          <span className={options.sub}>{item.sub}</span>
                        </span>
                        <span className={options.meta}>
                          {item.group === 'models' && (
                            item.score != null
                              ? <span className={options.score}><b>{(item.score * 100).toFixed(1)}%</b><small>fresh prompts</small></span>
                              : <span className={options.unmeasured}>Not measured</span>
                          )}
                          <span className={options.enter} aria-hidden="true"><CornerDownLeft size={13} /></span>
                        </span>
                      </li>
                    )
                  })}
                </ul>
              </li>
            ))}
          </ul>
          {flat.length === 0 && <p className={options.none}>No pages, models, or sections match <strong>“{query.trim()}”</strong>.</p>}
          {loadingModels && <p className={options.none}>Loading the models…</p>}
        </div>
        <div className={styles.footer}>
          <span className={styles.keys}><kbd>↑</kbd><kbd>↓</kbd> move</span>
          <span className={styles.keys}><kbd>Enter</kbd> open</span>
          <span className={styles.keys}><kbd>Esc</kbd> close</span>
          <span className={styles.count} role="status" aria-live="polite">{flat.length} {flat.length === 1 ? 'result' : 'results'}</span>
        </div>
      </div>
    </div>
  )
}
