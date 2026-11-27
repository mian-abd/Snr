import { Check, Columns3, Link2, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { LearnedMatrixRow } from '../api/types'
import { CompareBars } from '../charts/CompareBars'
import { ModelPicker } from '../components/ModelPicker'
import { accessLabel, addedLabel, evaluationOf, modelViews, priorityLabel, priorityOrder, providerLabel, studyRouterName, useCatalog, useFinalReport, useLearnedReport, usePool, useStudyReports, type ModelView } from '../lib/data'
import { perMillion, pct, seconds, usd } from '../lib/format'
import { makerOf, modelColors } from '../lib/makers'
import { compareHref, contextLabel, freshShare, maxCompared, parseCompared, plainName, replaceRoute, served, shareOf, taskBenchmark, taskLabel, taskOrder, taskShareOf } from '../lib/measures'
import { availability, changedPrice, priceOf } from '../lib/models'
import { Link } from '../lib/Link'
import { useRoute } from '../lib/router'
import { Button, ChartCard, Empty, ModelLogo, Notice, PageHeader, Section, Segmented, Skeleton } from '../ui'
import styles from './compare.module.css'

type Better = 'high' | 'low'
type Cell = { value: number | null; text: ReactNode; bar?: number | null; sub?: ReactNode; muted?: boolean; title?: string }
type Row = { kind: 'row'; id: string; label: ReactNode; hint?: ReactNode; better?: Better; cells: Cell[] }
type Subhead = { kind: 'subhead'; id: string; title: string; about?: string }
type Group = { id: string; title: string; about?: string; rows: Array<Row | Subhead> }

/** A maker logo beside a name that already says who made it (hidden from screen readers). */
const Logo = (props: Parameters<typeof ModelLogo>[0]) => <span className={styles.logo} aria-hidden="true"><ModelLogo {...props} /></span>

const same = (a: number, b: number) => Math.abs(a - b) <= Math.abs(b) * 1e-9 + 1e-12

/** Columns holding the best value of a row; none when fewer than two values or all tie. */
function bestColumns(row: Row) {
  if (!row.better) return new Set<number>()
  const present = row.cells.map((cell) => cell.value).filter((value): value is number => value != null)
  if (present.length < 2) return new Set<number>()
  const best = row.better === 'high' ? Math.max(...present) : Math.min(...present)
  if (present.every((value) => same(value, best))) return new Set<number>()
  return new Set(row.cells.flatMap((cell, index) => (cell.value != null && same(cell.value, best) ? [index] : [])))
}

const missing = (text: ReactNode = '—', title?: string): Cell => ({ value: null, text, muted: true, title })

function accuracyRows(prefix: string, chosen: ModelView[], rowOf: (view: ModelView) => LearnedMatrixRow | undefined): Row[] {
  const overall: Row = {
    kind: 'row',
    id: `${prefix}-all`,
    label: 'All tasks',
    better: 'high',
    cells: chosen.map((view) => {
      const row = rowOf(view)
      const share = shareOf(row)
      if (share == null || !row) return row ? missing('No answers', 'Every call failed, so every prompt counts as wrong') : missing()
      return { value: share, text: pct(share), bar: share, sub: `${row.correct} of ${row.prompts}` }
    }),
  }
  const tasks: Row[] = taskOrder.map((task) => ({
    kind: 'row',
    id: `${prefix}-${task}`,
    label: taskLabel[task],
    hint: taskBenchmark[task],
    better: 'high',
    cells: chosen.map((view) => {
      const row = rowOf(view)
      const share = taskShareOf(row, task)
      return share == null ? missing() : { value: share, text: pct(share), bar: share, sub: `${row?.correct_by_task[task] ?? 0} of ${row?.prompts_by_task[task] ?? 0}` }
    }),
  }))
  return [overall, ...tasks]
}

function priceCell(view: ModelView, side: 'input' | 'output'): Cell {
  const snapshot = priceOf(view.pool)[side]
  const live = changedPrice(view)
  if (!live) return { value: snapshot, text: perMillion(snapshot) }
  return {
    value: live[side],
    text: <span className={styles.moved}>{perMillion(live[side])}</span>,
    sub: <>Live · snapshot {perMillion(snapshot)}</>,
    title: 'Live price from the provider catalog, changed since the dated snapshot',
  }
}

type QuickPick = { id: string; title: string; about: string; ids: string[] }
const counted = ['no', 'one', 'two', 'three', 'four']

function quickPicks(views: ModelView[]): QuickPick[] {
  const measured = views.filter(served)
  const byAccuracy = [...measured].sort((a, b) => (freshShare(b) ?? 0) - (freshShare(a) ?? 0))
  const top = Math.min(3, measured.length)
  const picks: QuickPick[] = [
    { id: 'accurate', title: `The ${counted[top]} most accurate`, about: 'Highest share right on the fresh prompts', ids: byAccuracy.slice(0, 3).map((view) => view.id) },
    { id: 'fastest', title: `The ${counted[top]} fastest`, about: 'Lowest median response time', ids: [...measured].sort((a, b) => (a.fresh?.median_latency_ms ?? Infinity) - (b.fresh?.median_latency_ms ?? Infinity)).slice(0, 3).map((view) => view.id) },
    { id: 'free', title: 'Best without a bill', about: 'The most accurate free and local models', ids: byAccuracy.filter((view) => view.pool.access !== 'paid').slice(0, 3).map((view) => view.id) },
  ]
  const flagships = views.filter((view) => view.added === 'flagship').map((view) => view.id)
  if (flagships.length >= 2) picks.push({ id: 'flagships', title: 'The flagships', about: 'The large models added in the flagship study', ids: flagships.slice(0, maxCompared) })
  else {
    const cheapest = [...measured].filter((view) => view.pool.access === 'paid').sort((a, b) => (a.fresh?.cost_usd ?? Infinity) - (b.fresh?.cost_usd ?? Infinity))[0]
    const best = byAccuracy[0]
    if (cheapest && best && cheapest.id !== best.id) picks.push({ id: 'value', title: 'Cheapest against strongest', about: 'The cheapest paid model and the most accurate one', ids: [cheapest.id, best.id] })
  }
  return picks.filter((pick) => pick.ids.length >= 2)
}

export function ComparePage() {
  const { query } = useRoute()
  const pool = usePool()
  const catalog = useCatalog()
  const learned = useLearnedReport()
  const final = useFinalReport()
  const studies = useStudyReports()
  const [chart, setChart] = useState<'fresh' | 'suite'>('fresh')
  const [copied, setCopied] = useState<'idle' | 'done' | 'failed'>('idle')
  useEffect(() => {
    if (copied === 'idle') return
    const timer = window.setTimeout(() => setCopied('idle'), 2400)
    return () => window.clearTimeout(timer)
  }, [copied])

  const views = modelViews(pool.data, catalog.data, learned.data, final.data, studies)
  const byId = new Map(views.map((view) => [view.id, view]))
  const requested = parseCompared(query.get('models'))
  const chosen = requested.map((id) => byId.get(id)).filter((view): view is ModelView => Boolean(view))
  const ids = chosen.map((view) => view.id)
  const unknown = pool.data ? requested.filter((id) => !byId.has(id)) : []
  const colors = modelColors(ids)
  const setIds = (next: string[]) => replaceRoute(compareHref(next))
  const fresh = evaluationOf(final.data, 'final')
  const freshPrompts = fresh?.prompts ?? chosen.find((view) => view.fresh)?.fresh?.prompts ?? 300
  const suitePrompts = chosen.find((view) => view.suite)?.suite?.prompts ?? 600
  const hasSuite = chosen.some((view) => view.suite)
  const chartSet = chart === 'suite' && hasSuite ? 'suite' : 'fresh'

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied('done')
    } catch {
      setCopied('failed')
    }
  }

  const header = (
    <PageHeader
      title="Compare models"
      description={`Up to ${maxCompared} models side by side on the same prompts: accuracy by task, cost, speed, price, and how often the router picks each. The address keeps the selection, so a comparison can be shared as a link.`}
    />
  )
  if (pool.isLoading) return <>{header}<Skeleton height={420} /></>
  if (!pool.data) return <>{header}<Empty title="No model pool loaded">The router has not been trained on this server yet.</Empty></>

  const routers = [
    { id: 'frozen', title: 'Frozen router', about: `The adaptive router as frozen, on the ${freshPrompts} fresh prompts`, evaluation: fresh },
    ...studies.map((study) => ({ id: study.study_id, title: studyRouterName[study.study_id] ?? study.title, about: `${study.title}: the router refit with the same recipe on the wider pool`, evaluation: study.evaluations.find((item) => item.evaluation_id === 'final') })),
  ].filter((router) => router.evaluation)

  const groups: Group[] = [
    {
      id: 'overview',
      title: 'Overview',
      rows: [
        { kind: 'row', id: 'maker', label: 'Maker', cells: chosen.map((view) => ({ value: null, text: <span className={styles.maker}><Logo id={view.id} size={16} />{makerOf(view.id).name}</span> })) },
        { kind: 'row', id: 'access', label: 'Access', cells: chosen.map((view) => ({ value: null, text: accessLabel[view.pool.access] ?? view.pool.access, sub: view.added ? `Added in the ${addedLabel[view.added]?.toLowerCase() ?? view.added} study` : providerLabel[view.pool.provider] ?? view.pool.provider })) },
        { kind: 'row', id: 'size', label: 'Size', cells: chosen.map((view) => ({ value: null, text: view.pool.parameters, sub: view.pool.open_weight ? 'Open weights' : 'Closed weights' })) },
        { kind: 'row', id: 'status', label: 'Live status', cells: chosen.map((view) => { const state = availability(view); return { value: null, text: <span className={styles.status} data-tone={state.tone}><i aria-hidden="true" />{state.text}</span> } }) },
      ],
    },
    { id: 'fresh', title: `Accuracy on the ${freshPrompts} fresh prompts`, about: 'Share answered correctly; code passes only when every hidden test passes, and a failed call counts as wrong.', rows: accuracyRows('fresh', chosen, (view) => view.fresh) },
    ...(hasSuite ? [{ id: 'suite', title: `Accuracy on the ${suitePrompts}-prompt suite`, about: 'The original benchmark suite the routers were trained and tuned on.', rows: accuracyRows('suite', chosen, (view) => view.suite) }] : []),
    {
      id: 'cost',
      title: 'Cost and speed',
      about: `Measured on the same ${freshPrompts} fresh prompts.`,
      rows: [
        { kind: 'row', id: 'billed', label: 'Billed cost', hint: `All ${freshPrompts} fresh prompts`, better: 'low', cells: chosen.map((view) => (served(view) && view.fresh ? { value: view.fresh.cost_usd, text: usd(view.fresh.cost_usd), sub: view.fresh.correct ? `${usd(view.fresh.cost_usd / view.fresh.correct)} per right answer` : undefined } : missing())) },
        { kind: 'row', id: 'latency', label: 'Median response time', hint: 'Per prompt, successful calls', better: 'low', cells: chosen.map((view) => (served(view) && view.fresh?.median_latency_ms != null ? { value: view.fresh.median_latency_ms, text: seconds(view.fresh.median_latency_ms) } : missing())) },
      ],
    },
    {
      id: 'price',
      title: 'Price and context',
      about: 'Per million tokens; a live price from the provider catalog replaces the snapshot where they differ.',
      rows: [
        { kind: 'row', id: 'input', label: 'Input price', hint: 'Per million tokens', better: 'low', cells: chosen.map((view) => priceCell(view, 'input')) },
        { kind: 'row', id: 'output', label: 'Output price', hint: 'Per million tokens', better: 'low', cells: chosen.map((view) => priceCell(view, 'output')) },
        { kind: 'row', id: 'context', label: 'Context window', better: 'high', cells: chosen.map((view) => ({ value: view.pool.context_length, text: contextLabel(view.pool.context_length), sub: `${view.pool.context_length.toLocaleString('en-US')} tokens` })) },
      ],
    },
    ...(routers.length ? [{
      id: 'routing',
      title: 'How often the router picks it',
      about: `Share of the ${freshPrompts} fresh prompts each router sent to the model, at each priority.`,
      rows: routers.flatMap((router): Array<Row | Subhead> => {
        const evaluation = router.evaluation!
        const pool = new Set(evaluation.models)
        const rows: Row[] = priorityOrder.flatMap((priority) => {
          const strategy = evaluation.strategies.find((item) => item.strategy_id === `learned:${priority}`)
          if (!strategy) return []
          const total = Object.values(strategy.selected_models).reduce((sum, n) => sum + n, 0)
          return [{
            kind: 'row' as const,
            id: `${router.id}-${priority}`,
            label: priorityLabel[priority],
            better: 'high' as const,
            cells: chosen.map((view) => {
              if (!pool.has(view.id)) return missing('Not in its pool', 'This router could not choose the model')
              const n = strategy.selected_models[view.id] ?? 0
              const share = total ? n / total : 0
              return { value: share, text: `${Math.round(share * 100)}%`, bar: share, sub: `${n} of ${total}` }
            }),
          }]
        })
        return rows.length ? [{ kind: 'subhead', id: router.id, title: router.title, about: router.about }, ...rows] : []
      }),
    }] : []),
  ]

  const chartGroups = [
    { id: 'all', label: 'All tasks', values: chosen.map((view) => shareOf(chartSet === 'fresh' ? view.fresh : view.suite)) },
    ...taskOrder.map((task) => ({ id: task, label: taskLabel[task], values: chosen.map((view) => taskShareOf(chartSet === 'fresh' ? view.fresh : view.suite, task)) })),
  ]

  return (
    <>
      {header}
      <div className={styles.toolbar}>
        <div className={styles.toolbarStart}>
          <ModelPicker views={views} chosen={ids} full={ids.length >= maxCompared} onPick={(id) => setIds([...ids, id])} />
          <span className={styles.count}>{ids.length} of {maxCompared} chosen</span>
        </div>
        {ids.length > 0 && (
          <div className={styles.toolbarEnd}>
            <span aria-live="polite" className={styles.copied}>{copied === 'done' ? 'Link copied' : copied === 'failed' ? 'Copy the address bar instead' : ''}</span>
            <Button size="sm" onClick={copy}><Link2 size={14} />Copy link</Button>
            <Button size="sm" variant="ghost" onClick={() => setIds([])}>Clear</Button>
          </div>
        )}
      </div>
      {unknown.length > 0 && (
        <div className={styles.notice}><Notice tone="warn">No model has the ID {unknown.map((id, index) => <span key={id}>{index > 0 && ', '}<code>{id}</code></span>)}, so the comparison leaves {unknown.length === 1 ? 'it' : 'them'} out.</Notice></div>
      )}

      {chosen.length === 0 ? (
        <div className={styles.empty}>
          <Columns3 size={22} aria-hidden="true" />
          <strong>Choose up to {maxCompared} models to compare</strong>
          <p>Add any model with the button above, tick models on the <Link to="/models">models page</Link>, or start from one of these.</p>
          <div className={styles.quickPicks}>
            {quickPicks(views).map((pick) => (
              <button key={pick.id} type="button" className={styles.quick} onClick={() => setIds(pick.ids)}>
                <span className={styles.quickLogos} aria-hidden="true">{pick.ids.map((id) => <ModelLogo key={id} id={id} size={20} local={byId.get(id)?.pool.access === 'local'} />)}</span>
                <strong>{pick.title}</strong>
                <span>{pick.ids.map((id) => plainName(byId.get(id)?.pool.display_name ?? id)).join(', ')}</span>
                <small>{pick.about}</small>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          <ChartCard
            metric="accuracy"
            level={2}
            title="Accuracy by task"
            subtitle={chartSet === 'fresh' ? `Share of the ${freshPrompts} fresh prompts answered correctly.` : `Share of the ${suitePrompts}-prompt suite answered correctly.`}
            tools={hasSuite ? <Segmented label="Prompt set" value={chartSet} onChange={setChart} options={[{ id: 'fresh', label: 'Fresh prompts' }, { id: 'suite', label: `${suitePrompts}-prompt suite` }]} /> : undefined}
          >
            <div className={styles.legend}>
              {chosen.map((view) => (
                <span key={view.id}>
                  <i style={{ background: colors.get(view.id) }} aria-hidden="true" />
                  <Logo id={view.id} size={16} local={view.pool.access === 'local'} />
                  {plainName(view.pool.display_name)}
                  {shareOf(chartSet === 'fresh' ? view.fresh : view.suite) == null && <small className={styles.legendNote}>no answers</small>}
                </span>
              ))}
            </div>
            <CompareBars
              label={`Accuracy by task on the ${chartSet === 'fresh' ? `${freshPrompts} fresh prompts` : `${suitePrompts}-prompt suite`}`}
              series={chosen.map((view) => ({ id: view.id, name: plainName(view.pool.display_name), color: colors.get(view.id) ?? makerOf(view.id).color }))}
              groups={chartGroups}
              format={(value) => `${Math.round(value * 100)}%`}
            />
          </ChartCard>

          <Section id="side-by-side" title="Side by side" description={ids.length === 1 ? 'Add another model to see which one does better in each row.' : 'Each row marks the best value: the highest accuracy, context, and router share, and the lowest cost, time, and price. Ties share it.'}>
            <div className={styles.tableWrap}>
              <table className={styles.table} aria-label="Model comparison" style={{ ['--cols' as string]: chosen.length }}>
                <thead>
                  <tr>
                    <td className={styles.corner} />
                    {chosen.map((view) => {
                      const name = plainName(view.pool.display_name)
                      return (
                        <th key={view.id} scope="col" className={styles.modelCol}>
                          <div className={styles.modelHead}>
                            <span className={styles.modelKey} style={{ background: colors.get(view.id) }} aria-hidden="true" />
                            <Logo id={view.id} size={30} framed local={view.pool.access === 'local'} />
                            <div className={styles.modelText}>
                              <Link to={`/models/${encodeURIComponent(view.id)}`} className={styles.modelName}>{name}</Link>
                              <span className={styles.modelSub}>{makerOf(view.id).name}</span>
                            </div>
                            <button type="button" className={styles.remove} onClick={() => setIds(ids.filter((id) => id !== view.id))} aria-label={`Remove ${name} from the comparison`} title="Remove"><X size={14} /></button>
                          </div>
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                {groups.map((group) => (
                  <tbody key={group.id}>
                    <tr className={styles.groupRow}>
                      <th scope="colgroup" colSpan={chosen.length + 1}>
                        <span className={styles.sticky}><strong>{group.title}</strong>{group.about && <small>{group.about}</small>}</span>
                      </th>
                    </tr>
                    {group.rows.map((row) => {
                      if (row.kind === 'subhead') {
                        return (
                          <tr key={row.id} className={styles.subRow}>
                            <th scope="colgroup" colSpan={chosen.length + 1}><span className={styles.sticky}>{row.title}{row.about && <small>{row.about}</small>}</span></th>
                          </tr>
                        )
                      }
                      const best = bestColumns(row)
                      return (
                        <tr key={row.id}>
                          <th scope="row" className={styles.rowLabel}>
                            <span>{row.label}</span>
                            {row.hint && <small>{row.hint}</small>}
                          </th>
                          {row.cells.map((cell, index) => {
                            const view = chosen[index]
                            const isBest = best.has(index)
                            return (
                              <td key={view.id} className={`${isBest ? styles.best : ''} ${cell.muted ? styles.mutedCell : ''}`} title={cell.title}>
                                <div className={styles.cell}>
                                  <span className={styles.value}>
                                    {cell.text}
                                    {isBest && <span className={styles.bestTag}><Check size={11} strokeWidth={3} aria-hidden="true" />Best</span>}
                                  </span>
                                  {cell.bar != null && <span className={styles.track} aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(1, cell.bar)) * 100}%`, background: colors.get(view.id) }} /></span>}
                                  {cell.sub && <span className={styles.sub}>{cell.sub}</span>}
                                </div>
                              </td>
                            )
                          })}
                        </tr>
                      )
                    })}
                  </tbody>
                ))}
              </table>
            </div>
            <p className={styles.note}>
              Accuracy counts a failed call as a wrong answer, and the median time counts only the calls that came back. Models added in a pool study were never seen by the frozen router, so only that study’s router can pick them. <Link to="/research?section=method">How these were measured</Link>
            </p>
          </Section>
        </>
      )}
    </>
  )
}
