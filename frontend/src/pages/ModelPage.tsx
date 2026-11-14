import { BarChart3, ChevronRight, Coins, ShieldCheck, Shuffle } from 'lucide-react'
import { PairedBars, BarList } from '../charts/Charts'
import { accessLabel, evaluationOf, find, modelViews, priorityLabel, priorityOrder, providerLabel, useCatalog, useFinalReport, useLearnedReport, usePool } from '../lib/data'
import { perMillion, pct, seconds, shortTime, usd } from '../lib/format'
import { availability, changedPrice, priceOf } from '../lib/models'
import { Link } from '../lib/Link'
import { Badge, Card, Empty, ModelAvatar, Notice, Section, Skeleton, Stat } from '../ui'
import ui from '../ui/ui.module.css'
import styles from './pages.module.css'

const taskNames: Record<string, string> = { math: 'Math (GSM8K)', qa: 'Knowledge (MMLU-Pro)', code: 'Code (HumanEval+, MBPP+)' }
const sections = [
  { id: 'performance', label: 'Performance', icon: BarChart3 },
  { id: 'usage', label: 'When it is chosen', icon: Shuffle },
  { id: 'pricing', label: 'Price and availability', icon: Coins },
  { id: 'policy', label: 'Data policy', icon: ShieldCheck },
]

export function ModelPage({ id }: { id: string }) {
  const pool = usePool()
  const catalog = useCatalog()
  const learned = useLearnedReport()
  const final = useFinalReport()
  const views = modelViews(pool.data, catalog.data, learned.data, final.data)
  const view = views.find((item) => item.id === id)
  const fresh = evaluationOf(final.data, 'final')

  if (pool.isLoading) return <div style={{ paddingTop: '3rem' }}><Skeleton height={400} /></div>
  if (!view) return <div style={{ paddingTop: '3rem' }}><Empty title="Model not found"><Link to="/models">Back to all models</Link></Empty></div>

  const model = view.pool
  const price = priceOf(model)
  const live = changedPrice(view)
  const state = availability(view)
  const accuracy = view.fresh?.prompts ? view.fresh.correct / view.fresh.prompts : null
  const hosts = (model.request_options.provider as { order?: string[] } | undefined)?.order ?? []
  const shares = fresh
    ? priorityOrder.map((priority) => {
        const strategy = find(fresh.strategies, `learned:${priority}`)
        const total = strategy ? Object.values(strategy.selected_models).reduce((sum, n) => sum + n, 0) : 0
        const n = strategy?.selected_models[model.id] ?? 0
        return { id: priority, label: priorityLabel[priority], value: total ? n / total : 0, display: total ? `${Math.round((n / total) * 100)}%` : '—' }
      })
    : []

  return (
    <>
      <nav className={styles.crumbs} aria-label="Breadcrumb"><Link to="/models">Models</Link><ChevronRight size={14} /><span>{model.display_name}</span></nav>
      <div className={styles.modelHero}>
        <ModelAvatar model={model} size={52} />
        <div>
          <h1>{model.display_name}</h1>
          <div className={styles.row} style={{ marginTop: '0.4rem' }}>
            <code>{model.upstream_model}</code>
            <Badge tone={model.access === 'paid' ? 'neutral' : 'accent'}>{accessLabel[model.access]}</Badge>
            <Badge tone={state.tone} dot>{state.text}</Badge>
          </div>
        </div>
      </div>
      <p className={styles.body} style={{ maxWidth: '50rem' }}>
        {model.family} model, {model.parameters}{model.open_weight ? ', with open weights' : ''}. Reached through {providerLabel[model.provider] ?? model.provider}{hosts.length ? `, pinned to ${hosts.join(', ')}` : ''}.
        {!view.inRouter && ' Its free service failed repeated smoke tests (overloaded or timing out), so it has no measured results and the router never picks it.'}
      </p>
      <div className={styles.grid4} style={{ marginTop: '1.25rem' }}>
        <Stat label="Right on fresh prompts" value={accuracy != null ? pct(accuracy) : '—'} hint={view.fresh ? `${view.fresh.correct} of ${view.fresh.prompts}` : 'Not measured'} />
        <Stat label="Median response time" value={seconds(view.fresh?.median_latency_ms ?? view.suite?.median_latency_ms)} hint={view.fresh?.failed_calls ? `${view.fresh.failed_calls} failed calls` : 'Successful calls only'} />
        {price.input === 0 && price.output === 0
          ? <Stat label="Price per M tokens" value="Free" hint={model.access === 'local' ? 'Runs on this computer' : 'Free tier'} />
          : <Stat label="Price per M tokens (in / out)" value={live ? `${perMillion(live.input)} / ${perMillion(live.output)}` : `${perMillion(price.input)} / ${perMillion(price.output)}`} was={live ? `${perMillion(price.input)} / ${perMillion(price.output)}` : undefined} hint={live ? `Live price, ${live.output < price.output ? 'lower' : 'higher'} than the snapshot` : 'Unchanged since the snapshot'} />}
        <Stat label="Context window" value={`${(model.context_length / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })}K`} hint={`${model.context_length.toLocaleString()} tokens`} />
      </div>

      <div className={styles.withNav}>
        <nav className={styles.sideNav} aria-label="On this page">
          {sections.map((section) => {
            const Icon = section.icon
            return <a key={section.id} href={`#/models/${encodeURIComponent(id)}`} onClick={(event) => { event.preventDefault(); document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth' }) }}><Icon size={15} />{section.label}</a>
          })}
        </nav>
        <div>
          <Section id="performance" icon={<BarChart3 size={18} />} title="Performance by task" description="Share of prompts answered correctly. Code passes only when every hidden test passes; a failed call counts as wrong.">
            {view.suite || view.fresh ? (
              <Card>
                <PairedBars
                  max={1}
                  series={[{ name: `Original ${view.suite?.prompts ?? 600} prompts`, color: 'var(--series-1)' }, { name: `Fresh ${view.fresh?.prompts ?? 300} prompts`, color: 'var(--series-2)' }]}
                  rows={['math', 'qa', 'code'].map((task) => {
                    const a = view.suite && view.suite.prompts_by_task[task] ? view.suite.correct_by_task[task] / view.suite.prompts_by_task[task] : null
                    const b = view.fresh && view.fresh.prompts_by_task[task] ? view.fresh.correct_by_task[task] / view.fresh.prompts_by_task[task] : null
                    return { id: task, label: taskNames[task], values: [a, b], displays: [a == null ? '—' : pct(a, 0), b == null ? '—' : pct(b, 0)] }
                  })}
                />
              </Card>
            ) : <Empty title="Not measured">This model has no benchmark results.</Empty>}
          </Section>

          <Section id="usage" icon={<Shuffle size={18} />} title="When the router chooses it" description={`Share of the ${fresh?.prompts ?? 300} fresh prompts the adaptive router sent to this model, for each priority.`}>
            {shares.length ? <Card><BarList data={shares} max={1} label="Share of prompts per priority" /></Card> : <Empty title="No routing results yet" />}
          </Section>

          <Section id="pricing" icon={<Coins size={18} />} title="Price and availability" description="What the provider charges and whether it still serves the model, from the dated snapshot and the latest live check.">
            <div className={ui.tableWrap}>
              <table className={ui.table}>
                <tbody>
                  <tr><td>Snapshot price (in / out per M tokens)</td><td className={ui.num}>{price.input === 0 && price.output === 0 ? 'Free' : `${perMillion(price.input)} / ${perMillion(price.output)}`}</td></tr>
                  <tr><td>Live price</td><td className={ui.num}>{view.status?.live_prompt_price_per_million != null ? `${perMillion(view.status.live_prompt_price_per_million)} / ${perMillion(view.status.live_completion_price_per_million ?? 0)}` : 'Not reported'}</td></tr>
                  <tr><td>Status</td><td>{view.status?.note ?? (view.inRouter ? 'Not checked yet' : 'Not in the router')}</td></tr>
                  {hosts.length > 0 && <tr><td>Pinned hosts</td><td className={ui.num}>{hosts.join(', ')}</td></tr>}
                  {view.status && view.status.missing_hosts.length > 0 && <tr><td>Hosts no longer serving it</td><td className={ui.num}>{view.status.missing_hosts.join(', ')}</td></tr>}
                  <tr><td>Paid cost of its fresh-prompt answers</td><td className={ui.num}>{view.fresh ? usd(view.fresh.cost_usd) : '—'}</td></tr>
                  <tr><td>Last checked</td><td>{shortTime(catalog.data?.checked_at_utc ?? null)}</td></tr>
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="policy" icon={<ShieldCheck size={18} />} title="Data policy" description="What happens to a prompt sent to this model.">
            <Notice tone={model.access === 'local' ? 'good' : 'info'}>
              {model.data_policy}{model.api_key_env ? ` Needs ${model.api_key_env} on the server.` : ' No account or key needed.'}
            </Notice>
          </Section>
        </div>
      </div>
    </>
  )
}
