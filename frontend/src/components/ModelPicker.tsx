import { Plus, Search } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { accessLabel, addedLabel, type ModelView } from '../lib/data'
import { makerOf } from '../lib/makers'
import { freshShare, plainName } from '../lib/measures'
import { rankScore } from '../lib/search'
import { ModelLogo } from '../ui'
import ui from '../ui/ui.module.css'
import { MatchText } from './MatchText'
import options from './options.module.css'
import styles from './ModelPicker.module.css'

/** An "Add a model" button that opens a searchable list of the models not chosen yet. */
export function ModelPicker({ views, chosen, onPick, full, label = 'Add a model' }: {
  views: ModelView[]
  chosen: string[]
  onPick: (id: string) => void
  /** No room for another model. */
  full?: boolean
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const wrapRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  const optionId = (index: number) => `${listId}-${index}`

  const found = useMemo(() => views
    .filter((view) => !chosen.includes(view.id))
    .map((view) => {
      const maker = makerOf(view.id)
      return { view, maker, share: freshShare(view), rank: query.trim() ? rankScore(query, plainName(view.pool.display_name), `${maker.name} ${view.id} ${view.pool.family} ${view.pool.access} ${view.added ?? ''}`) : 0 }
    })
    .filter((entry) => entry.rank != null)
    .sort((a, b) => (query.trim() ? (b.rank ?? 0) - (a.rank ?? 0) : (b.share ?? -1) - (a.share ?? -1))), [views, chosen, query])
  const current = found.length ? Math.min(active, found.length - 1) : -1

  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
    const outside = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [open])

  useEffect(() => {
    if (open && current >= 0) document.getElementById(optionId(current))?.scrollIntoView?.({ block: 'nearest' })
    // optionId only depends on the stable list ID.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, current])

  const close = (refocus = true) => {
    setOpen(false)
    setQuery('')
    setActive(0)
    if (refocus) buttonRef.current?.focus()
  }
  const pick = (id: string | undefined) => {
    if (!id) return
    onPick(id)
    close()
  }
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!found.length) return
      setActive((current + (event.key === 'ArrowDown' ? 1 : -1) + found.length) % found.length)
    } else if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
      event.preventDefault()
      pick(found[current]?.view.id)
    } else if (event.key === 'Tab') {
      close(false)
    }
  }

  return (
    <div className={styles.picker} ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className={`${ui.button} ${ui.secondary}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={full}
        title={full ? 'Four models is the most the page shows side by side; remove one first' : undefined}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <Plus size={15} />{label}
      </button>
      {open && (
        <div className={styles.popover}>
          <div className={styles.searchRow}>
            <Search size={15} aria-hidden="true" />
            <input
              ref={inputRef}
              className={styles.input}
              type="text"
              role="combobox"
              aria-label="Find a model to add"
              aria-expanded="true"
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={current >= 0 ? optionId(current) : undefined}
              placeholder="Find a model, maker, or access"
              autoComplete="off"
              spellCheck={false}
              value={query}
              onChange={(event) => { setQuery(event.target.value); setActive(0) }}
              onKeyDown={onKeyDown}
            />
          </div>
          <ul id={listId} role="listbox" aria-label="Models" className={`${options.list} ${styles.list}`}>
            {found.map(({ view, maker, share }, index) => (
              <li
                key={view.id}
                id={optionId(index)}
                role="option"
                aria-selected={index === current}
                className={options.option}
                onMouseMove={() => { if (index !== current) setActive(index) }}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(view.id)}
              >
                <span className={options.icon} aria-hidden="true"><ModelLogo id={view.id} size={18} local={view.pool.access === 'local'} /></span>
                <span className={options.text}>
                  <span className={options.title}><MatchText text={plainName(view.pool.display_name)} query={query} /></span>
                  <span className={options.sub}>{maker.name} · {accessLabel[view.pool.access] ?? view.pool.access}{view.added ? ` · ${addedLabel[view.added] ?? 'Added'}` : ''}</span>
                </span>
                <span className={options.meta}>
                  {share != null ? <span className={options.score}><b>{(share * 100).toFixed(1)}%</b><small>fresh prompts</small></span> : <span className={options.unmeasured}>Not measured</span>}
                </span>
              </li>
            ))}
          </ul>
          {found.length === 0 && <p className={options.none}>{chosen.length && !query.trim() ? 'Every model is already chosen.' : <>No model matches <strong>“{query.trim()}”</strong>.</>}</p>}
        </div>
      )}
    </div>
  )
}
