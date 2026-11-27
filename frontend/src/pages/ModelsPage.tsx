import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, ArrowUpRight, Columns3, Download, RefreshCw, Satellite } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { LiveCatalogStatus } from '../api/types'
import { downloadText, toCsv, type CsvValue } from '../lib/csv'
import { accessLabel, addedLabel, catalogKey, modelViews, providerLabel, useCatalog, useFinalReport, useLearnedReport, usePool, useStudyReports, type ModelView } from '../lib/data'
import { perMillion, seconds, shortTime, usd } from '../lib/format'
import { makerOf, makersIn } from '../lib/makers'
import { compareHref, contextLabel, freshShare, maxCompared, plainName, served, taskShare } from '../lib/measures'
import { availability, changedPrice, priceOf } from '../lib/models'
import { Link } from '../lib/Link'
import { navigate } from '../lib/router'
import { Button, Empty, ModelLogo, Notice, PageHeader, Segmented, Skeleton } from '../ui'
import ui from '../ui/ui.module.css'
import styles from './models.module.css'

type Filter = 'all' | 'paid' | 'free' | 'local' | 'flagship' | 'budget'
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
const percent = (value: number | null) => (value == null ? '—' : `${Math.round(value * 100)}%`)
const round = (value: number, digits: number) => Number(value.toFixed(digits))

function Score({ value }: { value: number | null }) {
  if (value == null) return <span className={ui.muted}>—</span>
  return (
    <span className={styles.score}>
      <span className={styles.scoreValue}>{Math.round(value * 100)}%</span>
      <span className={styles.scoreTrack} aria-hidden="true"><span style={{ width: `${value * 100}%` }} /></span>
    </span>
  )
}

/** The table's rows and columns as CSV: numbers unrounded, units in the headers. */
function tableCsv(rows: ModelView[], freshPrompts: number) {
  const header = [
    'Model', 'Maker', 'Access', 'Added in study',
    `Accuracy, all tasks (% of ${freshPrompts} fresh prompts)`, 'Accuracy, math (%)', 'Accuracy, knowledge (%)', 'Accuracy, code (%)',
    'Input price (USD per M tokens)', 'Output price (USD per M tokens)', 'Billed cost, all prompts (USD)', 'Median time per prompt (s)', 'Context (tokens)', 'Status',
  ]
  const share = (value: number | null) => (value == null ? null : round(value * 100, 2))
  const body: CsvValue[][] = rows.map((view) => {
    const price = changedPrice(view) ?? priceOf(view.pool)
    const isServed = served(view)
    return [
      plainName(view.pool.display_name),
      makerOf(view.id).name,
      accessLabel[view.pool.access] ?? view.pool.access,
      view.added ? addedLabel[view.added] ?? view.added : null,
      share(freshShare(view)),
      share(taskShare(view, 'math')),
      share(taskShare(view, 'qa')),
      share(taskShare(view, 'code')),
      Number(price.input.toPrecision(6)),
      Number(price.output.toPrecision(6)),
      isServed && view.fresh ? round(view.fresh.cost_usd, 6) : null,
      isServed && view.fresh?.median_latency_ms != null ? round(view.fresh.median_latency_ms / 1000, 2) : null,
      view.pool.context_length,
      availability(view).text,
    ]
  })
  return toCsv([header, ...body])
}

export function ModelsPage() {
  const pool = usePool()
  const catalog = useCatalog()
  const learned = useLearnedReport()
  const final = useFinalReport()
  const studies = useStudyReports()
  const [filter, setFilter] = useState<Filter>('all')
  const [makerFilter, setMakerFilter] = useState<string[]>([])
  const [picked, setPicked] = useState<string[]>([])
  const [sort, setSort] = useState<{ key: SortKey; ascending: boolean }>({ key: 'fresh', ascending: false })
  const [query, setQuery] = useState('')
  const views = modelViews(pool.data, catalog.data, learned.data, final.data, studies)
  const groups = [...new Set(views.map((view) => view.added).filter((group): group is string => Boolean(group)))]
  const makers = makersIn(views.map((view) => view.id))
  // Each maker's chip wears the logo of its most accurate model (Gemini rather than Gemma for Google).
  const firstOf = new Map<string, string>()
  for (const view of [...views].sort((a, b) => (freshShare(b) ?? -1) - (freshShare(a) ?? -1))) if (!firstOf.has(makerOf(view.id).id)) firstOf.set(makerOf(view.id).id, view.id)
  const freshPrompts = final.data?.evaluations.find((item) => item.evaluation_id === 'final')?.prompts ?? 300
  const rows = views
    .filter((view) => filter === 'all' || (filter === 'flagship' || filter === 'budget' ? view.added === filter : view.pool.access === filter))
    .filter((view) => makerFilter.length === 0 || makerFilter.includes(makerOf(view.id).id))
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
  const nameOf = (id: string) => plainName(views.find((view) => view.id === id)?.pool.display_name ?? id)
  const toggleMaker = (id: string) => setMakerFilter((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]))
  const togglePicked = (id: string) => setPicked((current) => (current.includes(id) ? current.filter((item) => item !== id) : current.length < maxCompared ? [...current, id] : current))
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
          <Segmented label="Access" value={filter} onChange={setFilter} options={[{ id: 'all', label: 'All' }, { id: 'paid', label: 'Paid' }, { id: 'free', label: 'Free' }, { id: 'local', label: 'Local' }, ...groups.map((group) => ({ id: group as Filter, label: `${addedLabel[group] ?? group}${group === 'flagship' ? 's' : ''}` }))]} />
        </div>
        {pool.data && (
          <div className={styles.toolbar}>
            {makers.length > 1 ? (
              <div className={styles.makers} role="group" aria-label="Filter by maker">
                {makers.map((maker) => (
                  <button key={maker.id} type="button" className={styles.makerChip} aria-pressed={makerFilter.includes(maker.id)} onClick={() => toggleMaker(maker.id)}>
                    <span className={styles.chipLogo} aria-hidden="true"><ModelLogo id={firstOf.get(maker.id) ?? maker.id} size={15} /></span>{maker.name}
                  </button>
                ))}
                {makerFilter.length > 0 && <button type="button" className={styles.clearMakers} onClick={() => setMakerFilter([])}>All makers</button>}
              </div>
            ) : <span />}
            <Button size="sm" onClick={() => downloadText('models.csv', tableCsv(rows, freshPrompts))} disabled={rows.length === 0} title="The rows and columns shown, in this order">
              <Download size={14} />Download CSV
            </Button>
          </div>
        )}
        {pool.isLoading && <Skeleton height={420} />}
        {pool.data === null && <Empty title="No model pool loaded">The router has not been trained on this server yet.</Empty>}
        {pool.data && rows.length === 0 && <Empty title="No models match">Try another filter.</Empty>}
        {rows.length > 0 && (
          <div className={`${ui.tableWrap} ${styles.tableWrap}`}>
            <table className={`${ui.table} ${styles.table}`}>
              <thead>
                <tr className={styles.groupHead}>
                  <td />
                  <td />
                  <th colSpan={4}>Accuracy <small>on {freshPrompts} fresh prompts</small></th>
                  <th colSpan={3}>Price</th>
                  <th>Speed</th>
                  <th>Features</th>
                  <td />
                </tr>
                <tr>
                  <th className={styles.pickCol}><span className={styles.srOnly}>Pick to compare</span></th>
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
                  const isPicked = picked.includes(view.id)
                  const name = plainName(view.pool.display_name)
                  const dim = (!view.inRouter && !view.added) || state.tone === 'bad'
                  return (
                    <tr key={view.id} className={`${dim ? styles.dim : ''} ${isPicked ? styles.picked : ''}`}>
                      <td className={styles.pickCol}>
                        <input
                          type="checkbox"
                          className={styles.check}
                          checked={isPicked}
                          disabled={!isPicked && picked.length >= maxCompared}
                          onChange={() => togglePicked(view.id)}
                          aria-label={`Pick ${name} to compare`}
                          title={!isPicked && picked.length >= maxCompared ? `Up to ${maxCompared} models can be compared` : undefined}
                        />
                      </td>
                      <td className={styles.modelCell} style={{ ['--maker' as string]: maker.color }}>
                        <Link to={`/models/${encodeURIComponent(view.id)}`} className={styles.modelLink}>
                          <ModelLogo id={view.id} size={18} local={view.pool.access === 'local'} />
                          <span className={styles.modelName}>{name}</span>
                          <span className={styles.modelSub}>{maker.name} · {accessLabel[view.pool.access]}{view.added ? ` · ${addedLabel[view.added] ?? 'Added'}` : ''}</span>
                        </Link>
                      </td>
                      <td><Score value={freshShare(view)} /></td>
                      <td className={styles.center}>{percent(taskShare(view, 'math'))}</td>
                      <td className={styles.center}>{percent(taskShare(view, 'qa'))}</td>
                      <td className={styles.center}>{percent(taskShare(view, 'code'))}</td>
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
        {picked.length > 0 && (
          <div className={styles.compareBar} role="region" aria-label="Models picked to compare">
            <div className={styles.compareLogos} aria-hidden="true">
              {picked.map((id) => <ModelLogo key={id} id={id} size={20} framed local={views.find((view) => view.id === id)?.pool.access === 'local'} />)}
            </div>
            <p className={styles.compareText}>
              <strong>{picked.length} of {maxCompared} picked</strong>
              <span>{picked.map(nameOf).join(', ')}</span>
            </p>
            <div className={styles.compareActions}>
              <Button size="sm" variant="ghost" onClick={() => setPicked([])}>Clear</Button>
              <Button size="sm" variant="primary" onClick={() => navigate(compareHref(picked))}>
                <Columns3 size={14} />Compare {picked.length} {picked.length === 1 ? 'model' : 'models'}
              </Button>
            </div>
          </div>
        )}
        {pool.data && (
          <p className={styles.note}>
            Prices are per million input and output tokens; a model pinned to several hosts shows the highest. Highlighted prices come from the live catalog and differ from the dated snapshot of {pool.data.metadata_as_of.slice(0, 10)}. Models reach the router through {[...new Set(views.map((view) => providerLabel[view.pool.provider] ?? view.pool.provider))].join(', ')}. Tick up to {maxCompared} models to compare them side by side. <Link to="/research?section=method" className={styles.more}>How these were measured<ArrowUpRight size={13} /></Link>
          </p>
        )}
      </div>
    </>
  )
}
