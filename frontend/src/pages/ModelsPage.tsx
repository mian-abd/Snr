import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Boxes, RefreshCw, Satellite } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { LiveCatalogStatus } from '../api/types'
import { accessLabel, catalogKey, modelViews, providerLabel, useCatalog, useFinalReport, useLearnedReport, usePool, type ModelView } from '../lib/data'
import { perMillion, pct, seconds, shortTime } from '../lib/format'
import { availability, changedPrice, priceOf } from '../lib/models'
import { Link } from '../lib/Link'
import { Badge, Button, Empty, Meter, ModelAvatar, Notice, PageHeader, Segmented, Skeleton } from '../ui'
import ui from '../ui/ui.module.css'
import styles from './pages.module.css'

type Filter = 'all' | 'paid' | 'free' | 'local'
type Sort = 'accuracy' | 'price' | 'speed' | 'context'

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
      <div className={styles.between}>
        <span>{text}</span>
        <Button size="sm" onClick={() => refresh.mutate()} disabled={refresh.isPending}><RefreshCw size={14} />{refresh.isPending ? 'Checking…' : 'Check again'}</Button>
      </div>
    </Notice>
  )
}

function ModelRow({ view }: { view: ModelView }) {
  const price = priceOf(view.pool)
  const live = changedPrice(view)
  const state = availability(view)
  const accuracy = view.fresh && view.fresh.prompts ? view.fresh.correct / view.fresh.prompts : null
  const served = view.fresh ? view.fresh.prompts - view.fresh.failed_calls : 0
  return (
    <Link to={`/models/${encodeURIComponent(view.id)}`} className={`${styles.modelRow} ${!view.inRouter || state.tone === 'bad' ? styles.modelRowOut : ''}`}>
      <ModelAvatar model={view.pool} size={40} />
      <div className={styles.modelMain}>
        <div className={styles.modelTitle}>
          <strong>{view.pool.display_name}</strong>
          <Badge tone={view.pool.access === 'paid' ? 'neutral' : 'accent'}>{accessLabel[view.pool.access]}</Badge>
          {state.text !== 'Available' && <Badge tone={state.tone} dot>{state.text}</Badge>}
          {live && <Badge tone="good">Price cut</Badge>}
        </div>
        <span className={styles.modelSub}>{view.pool.family} · {view.pool.parameters}{view.pool.open_weight ? ' · open weights' : ''}</span>
        <div className={styles.modelMeta}>
          <span><b>{view.pool.context_length.toLocaleString()}</b> context</span>
          <span>
            {price.input === 0 && price.output === 0
              ? <b>Free</b>
              : live
                ? <><span className={styles.strike}>{perMillion(price.input)} / {perMillion(price.output)}</span><b className={styles.newPrice}>{perMillion(live.input)} / {perMillion(live.output)}</b> per M tokens</>
                : <><b>{perMillion(price.input)} / {perMillion(price.output)}</b> per M tokens</>}
          </span>
          {view.fresh?.median_latency_ms != null && served > 0 && <span>median <b>{seconds(view.fresh.median_latency_ms)}</b></span>}
          <span>via {providerLabel[view.pool.provider] ?? view.pool.provider}</span>
        </div>
      </div>
      <div className={styles.modelScore}>
        {accuracy != null && served > 0
          ? <><strong>{pct(accuracy, 0)}</strong><span>right on fresh prompts</span><Meter value={accuracy} label={`${pct(accuracy)} right`} /></>
          : <span>{view.inRouter ? 'No answers served' : 'Not measured'}</span>}
      </div>
    </Link>
  )
}

export function ModelsPage() {
  const pool = usePool()
  const catalog = useCatalog()
  const learned = useLearnedReport()
  const final = useFinalReport()
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<Sort>('accuracy')
  const [query, setQuery] = useState('')
  const views = modelViews(pool.data, catalog.data, learned.data, final.data)
  const score = (view: ModelView) => (view.fresh?.prompts ? view.fresh.correct / view.fresh.prompts : -1)
  const sorted = views
    .filter((view) => filter === 'all' || view.pool.access === filter)
    .filter((view) => `${view.pool.display_name} ${view.id} ${view.pool.family}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => {
      if (sort === 'price') return priceOf(a.pool).output - priceOf(b.pool).output
      if (sort === 'speed') return (a.fresh?.median_latency_ms ?? 1e12) - (b.fresh?.median_latency_ms ?? 1e12)
      if (sort === 'context') return b.pool.context_length - a.pool.context_length
      return score(b) - score(a)
    })

  return (
    <>
      <PageHeader
        eyebrow={<><Boxes size={15} />Models</>}
        title="The models the router chooses from"
        description="Eleven open and closed models across three ways to reach them: paid and free APIs, and one running on this computer. Accuracy is measured on the same 300 fresh prompts for every model the router uses; availability and prices are checked live against the providers."
      />
      <div className={styles.stack}>
        <CatalogBar status={catalog.data} />
        <div className={styles.toolbar}>
          <input className={ui.input} type="search" placeholder="Search models" aria-label="Search models" value={query} onChange={(event) => setQuery(event.target.value)} />
          <Segmented label="Access" value={filter} onChange={setFilter} options={[{ id: 'all', label: 'All' }, { id: 'paid', label: 'Paid' }, { id: 'free', label: 'Free' }, { id: 'local', label: 'Local' }]} />
          <select className={ui.select} style={{ width: 'auto' }} aria-label="Sort models" value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
            <option value="accuracy">Most accurate</option>
            <option value="price">Lowest price</option>
            <option value="speed">Fastest</option>
            <option value="context">Largest context</option>
          </select>
        </div>
        {pool.isLoading && <Skeleton height={300} />}
        {pool.data === null && <Empty icon={<Boxes size={22} />} title="No model pool loaded">The router has not been trained on this server yet.</Empty>}
        {pool.data && sorted.length === 0 && <Empty title="No models match">Try another search or filter.</Empty>}
        <div className={styles.modelList}>{sorted.map((view) => <ModelRow key={view.id} view={view} />)}</div>
        {pool.data && <p className={styles.small}>Prices are per million input / output tokens; a model pinned to several hosts shows the highest of them. Dated snapshot of {pool.data.metadata_as_of.slice(0, 10)}; struck-through prices were replaced by the live catalog.</p>}
      </div>
    </>
  )
}
