import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, ArrowUpRight, RefreshCw, Satellite } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { LiveCatalogStatus } from '../api/types'
import { accessLabel, catalogKey, modelViews, providerLabel, useCatalog, useFinalReport, useFlagshipReport, useLearnedReport, usePool, type ModelView } from '../lib/data'
import { perMillion, seconds, shortTime, usd } from '../lib/format'
import { makerOf } from '../lib/makers'
import { availability, changedPrice, priceOf } from '../lib/models'
import { Link } from '../lib/Link'
import { Button, Empty, ModelLogo, Notice, PageHeader, Segmented, Skeleton } from '../ui'
import ui from '../ui/ui.module.css'
import styles from './models.module.css'

type Filter = 'all' | 'paid' | 'free' | 'local' | 'flagship'
type SortKey = 'name' | 'fresh' | 'math' | 'qa' | 'code' | 'input' | 'output' | 'cost' | 'speed' | 'context'

export function CatalogBar({ status }: { status: LiveCatalogStatus | null | undefined }) {
  const queryClient = useQueryClient()
  const refresh = useMutation({ mutationFn: client.refreshCatalog, onSuccess: (data) => queryClient.setQueryData(catalogKey, data) })
  if (!status) return null
  const gone = status.models.filter((item) => !item.available)
  const text = status.source === 'live'
    ? <><strong>Provider catalogs checked {shortTime(status.checked_at_utc)}.</strong> {gone.length ? `${gone.map((item) => item.display_name).join(', ')} ${gone.length === 1 ? 'is' : 'are'} no longer served and will not be chosen.` : 'Every model is being served.'} Changed prices update expected costs right away.</>
    : <><strong>{status.source === 'snapshot' ? 'The live check failed' : 'The live check is off'}.</strong> Availability and prices come from the dated snapshot of {status.snapshot_as_of.slice(0, 10)}.</>
  return (
    <Notice tone={status.source === 'live' && !gone.length ? 'good' : 'warn'} icon={<Satellite size={16} />}>
      <div className={styles.catalog}>
        <span>{text}</span>
        <Button size="sm" onClick={() => refresh.mutate()} disabled={refresh.isPending}><RefreshCw size={14} />{refresh.isPending ? 'Checking…' : 'Check again'}</Button>
      </div>
    </Notice>
  )
}

const taskShare = (view: ModelView, task: string) => {
  const row = view.fresh
  const n = row?.prompts_by_task[task] ?? 0
  return row && n && row.failed_calls < row.prompts ? row.correct_by_task[task] / n : null
}
const served = (view: ModelView) => Boolean(view.fresh && view.fresh.failed_calls < view.fresh.prompts)
const freshShare = (view: ModelView) => (served(view) && view.fresh ? view.fresh.correct / view.fresh.prompts : null)

const sorters: Record<SortKey, (view: ModelView) => number | string | null> = {
  name: (view) => view.pool.display_name.toLowerCase(),
  fresh: freshShare,
  math: (view) => taskShare(view, 'math'),
  qa: (view) => taskShare(view, 'qa'),
  code: (view) => taskShare(view, 'code'),
  input: (view) => (changedPrice(view) ?? priceOf(view.pool)).input,
  output: (view) => (changedPrice(view) ?? priceOf(view.pool)).output,
  cost: (view) => (served(view) ? view.fresh?.cost_usd ?? null : null),
  speed: (view) => (served(view) ? view.fresh?.median_latency_ms ?? null : null),
  context: (view) => view.pool.context_length,
}
const ascendingFirst: SortKey[] = ['name', 'input', 'output', 'cost', 'speed']
const contextLabel = (tokens: number) => (tokens >= 1_000_000 ? `${Math.round(tokens / 100_000) / 10}M` : `${Math.round(tokens / 1000)}K`)

function Score({ value }: { value: number | null }) {
  if (value == null) return <span className={ui.muted}>—</span>
  return (
    <span className={styles.score}>
      <span className={styles.scoreValue}>{Math.round(value * 100)}%</span>
      <span className={styles.scoreTrack} aria-hidden="true"><span style={{ width: `${value * 100}%` }} /></span>
    </span>
  )
}

export function ModelsPage() {
  const pool = usePool()
  const catalog = useCatalog()
  const learned = useLearnedReport()
  const final = useFinalReport()
  const flagships = useFlagshipReport()
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<{ key: SortKey; ascending: boolean }>({ key: 'fresh', ascending: false })
  const [query, setQuery] = useState('')
  const views = modelViews(pool.data, catalog.data, learned.data, final.data, flagships.data)
  const freshPrompts = final.data?.evaluations.find((item) => item.evaluation_id === 'final')?.prompts ?? 300
  const rows = views
    .filter((view) => filter === 'all' || (filter === 'flagship' ? view.flagship : view.pool.access === filter))
    .filter((view) => `${view.pool.display_name} ${view.id} ${view.pool.family} ${makerOf(view.id).name}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => {
      const x = sorters[sort.key](a)
      const y = sorters[sort.key](b)
      if (x == null && y == null) return 0
      if (x == null) return 1
      if (y == null) return -1
      const order = typeof x === 'string' ? x.localeCompare(String(y)) : (x as number) - (y as number)
      return sort.ascending ? order : -order
    })
  const header = (key: SortKey, label: string, sub?: string) => {
    const active = sort.key === key
    return (
      <th aria-sort={active ? (sort.ascending ? 'ascending' : 'descending') : undefined}>
        <button type="button" className={styles.sortButton} onClick={() => setSort(active ? { key, ascending: !sort.ascending } : { key, ascending: ascendingFirst.includes(key) })}>
          <span>{label}{sub && <small>{sub}</small>}</span>
          {active ? (sort.ascending ? <ArrowUp size={13} /> : <ArrowDown size={13} />) : <ArrowDown size={13} className={styles.sortIdle} />}
        </button>
      </th>
    )
  }

  return (
    <>
      <PageHeader
        title="Models"
        description={`Every model the router can choose from, open and closed, reached through paid APIs, free APIs, and this computer. Accuracy, cost, and time are measured on the same ${freshPrompts} fresh prompts; availability and prices are checked live against the providers.`}
      />
      <div className={styles.stack}>
        <CatalogBar status={catalog.data} />
        <div className={styles.toolbar}>
          <input className={`${ui.input} ${styles.search}`} type="search" placeholder="Filter, e.g. Gemini, free, Google" aria-label="Filter models" value={query} onChange={(event) => setQuery(event.target.value)} />
          <Segmented label="Access" value={filter} onChange={setFilter} options={[{ id: 'all', label: 'All' }, { id: 'paid', label: 'Paid' }, { id: 'free', label: 'Free' }, { id: 'local', label: 'Local' }, ...(flagships.data ? [{ id: 'flagship' as const, label: 'Flagships' }] : [])]} />
        </div>
        {pool.isLoading && <Skeleton height={420} />}
        {pool.data === null && <Empty title="No model pool loaded">The router has not been trained on this server yet.</Empty>}
        {pool.data && rows.length === 0 && <Empty title="No models match">Try another filter.</Empty>}
        {rows.length > 0 && (
          <div className={`${ui.tableWrap} ${styles.tableWrap}`}>
            <table className={`${ui.table} ${styles.table}`}>
              <thead>
                <tr className={styles.groupHead}>
                  <th />
                  <th colSpan={4}>Accuracy <small>on {freshPrompts} fresh prompts</small></th>
                  <th colSpan={3}>Price</th>
                  <th>Speed</th>
                  <th>Features</th>
                  <th />
                </tr>
                <tr>
                  {header('name', 'Model')}
                  {header('fresh', 'All tasks')}
                  {header('math', 'Math')}
                  {header('qa', 'Knowledge')}
                  {header('code', 'Code')}
                  {header('input', 'Input', 'per M tokens')}
                  {header('output', 'Output', 'per M tokens')}
                  {header('cost', 'All prompts', 'billed')}
                  {header('speed', 'Median time', 'per prompt')}
                  {header('context', 'Context')}
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((view) => {
                  const price = changedPrice(view) ?? priceOf(view.pool)
                  const moved = changedPrice(view) != null
                  const state = availability(view)
                  const maker = makerOf(view.id)
                  const isServed = served(view)
                  return (
                    <tr key={view.id} className={(!view.inRouter && !view.flagship) || state.tone === 'bad' ? styles.dim : undefined}>
                      <td className={styles.modelCell} style={{ ['--maker' as string]: maker.color }}>
                        <Link to={`/models/${encodeURIComponent(view.id)}`} className={styles.modelLink}>
                          <ModelLogo id={view.id} size={18} local={view.pool.access === 'local'} />
                          <span className={styles.modelName}>{view.pool.display_name.replace(/\s*\((free|local)\)/i, '')}</span>
                          <span className={styles.modelSub}>{maker.name} · {accessLabel[view.pool.access]}{view.flagship ? ' · Flagship' : ''}</span>
                        </Link>
                      </td>
                      <td><Score value={freshShare(view)} /></td>
                      <td className={styles.center}>{taskShare(view, 'math') == null ? '—' : `${Math.round(taskShare(view, 'math')! * 100)}%`}</td>
                      <td className={styles.center}>{taskShare(view, 'qa') == null ? '—' : `${Math.round(taskShare(view, 'qa')! * 100)}%`}</td>
                      <td className={styles.center}>{taskShare(view, 'code') == null ? '—' : `${Math.round(taskShare(view, 'code')! * 100)}%`}</td>
                      <td className={styles.center}>{price.input === 0 && price.output === 0 ? 'Free' : <span className={moved ? styles.moved : undefined} title={moved ? 'Live price, changed since the snapshot' : undefined}>{perMillion(price.input)}</span>}</td>
                      <td className={styles.center}>{price.input === 0 && price.output === 0 ? 'Free' : <span className={moved ? styles.moved : undefined} title={moved ? 'Live price, changed since the snapshot' : undefined}>{perMillion(price.output)}</span>}</td>
                      <td className={styles.center}>{isServed && view.fresh ? usd(view.fresh.cost_usd) : '—'}</td>
                      <td className={styles.center}>{isServed ? seconds(view.fresh?.median_latency_ms) : '—'}</td>
                      <td className={styles.center}>{contextLabel(view.pool.context_length)}</td>
                      <td><span className={styles.status} data-tone={state.tone}><i />{state.text}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {pool.data && (
          <p className={styles.note}>
            Prices are per million input and output tokens; a model pinned to several hosts shows the highest. Highlighted prices come from the live catalog and differ from the dated snapshot of {pool.data.metadata_as_of.slice(0, 10)}. Models reach the router through {[...new Set(views.map((view) => providerLabel[view.pool.provider] ?? view.pool.provider))].join(', ')}. <Link to="/research?section=method" className={styles.more}>How these were measured<ArrowUpRight size={13} /></Link>
          </p>
        )}
      </div>
    </>
  )
}
