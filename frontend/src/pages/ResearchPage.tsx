import { AlertTriangle, BarChart3, BookOpen, Download, FlaskConical, Gauge, GraduationCap, ListOrdered, Scale, Search, Sigma, SlidersHorizontal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { client } from '../api/client'
import type { EvaluationSet, ExportTable, LearnedStrategyOutcome, PairedComparison, RoutingPriority } from '../api/types'
import { IntervalRow, Legend, PathChart } from '../charts/Charts'
import { ScatterChart, type ScatterPoint } from '../charts/ScatterChart'
import { evaluationLabel, evaluationOf, priorityLabel, priorityOrder, strategyFamily, strategyLabel, useFinalReport, useLearnedReport } from '../lib/data'
import { pct, pValue, seconds, signed, span, usd } from '../lib/format'
import { highlights } from '../lib/insights'
import { useRoute } from '../lib/router'
import { Badge, Card, Empty, Meter, PageHeader, Section, Segmented, Skeleton, Stat } from '../ui'
import ui from '../ui/ui.module.css'
import styles from './pages.module.css'

const views = [
  { id: 'all', label: 'All tasks' },
  { id: 'math', label: 'Math' },
  { id: 'qa', label: 'Knowledge' },
  { id: 'code', label: 'Code' },
]
const nav = [
  { id: 'highlights', label: 'Highlights', icon: BookOpen },
  { id: 'leaderboard', label: 'Leaderboard', icon: ListOrdered },
  { id: 'tradeoffs', label: 'Accuracy, cost, speed', icon: BarChart3 },
  { id: 'significance', label: 'Is it real?', icon: Sigma },
  { id: 'errors', label: 'Where it goes wrong', icon: Search },
  { id: 'robustness', label: 'When things change', icon: FlaskConical },
  { id: 'priorities', label: 'Your priorities', icon: SlidersHorizontal },
  { id: 'training', label: 'How it was built', icon: GraduationCap },
  { id: 'method', label: 'Method and limits', icon: Scale },
  { id: 'downloads', label: 'Downloads', icon: Download },
]
const exportTables: Array<{ id: ExportTable; label: string; about: string }> = [
  { id: 'strategies', label: 'Leaderboard', about: 'Every strategy with 95% intervals and per-task results' },
  { id: 'comparisons', label: 'Significance tests', about: 'The paired comparisons, with McNemar and Holm-adjusted p-values' },
  { id: 'errors', label: 'Routing errors', about: 'Errors and the hindsight gap, per priority and task' },
  { id: 'robustness', label: 'Robustness scenarios', about: 'Every scenario, router variant, and baseline' },
  { id: 'sweep', label: 'Priority sweep', about: 'Accuracy, cost, and time as one weight varies' },
  { id: 'decisions', label: 'Every decision', about: 'Which model each strategy chose on every prompt, and how it went' },
  { id: 'cells', label: 'Every model answer', about: 'Each model\'s graded outcome on every prompt (no response text)' },
]
const groups: Array<{ title: string; match: (id: string) => boolean }> = [
  { title: 'Adaptive router', match: (id) => strategyFamily(id) === 'learned' },
  { title: 'Single model and rule-based baselines', match: (id) => ['fixed', 'rule'].includes(strategyFamily(id)) && !id.endsWith('no_catalog') },
  { title: 'References', match: (id) => ['model_task_prior', 'learned_no_catalog', 'oracle'].includes(strategyFamily(id)) || id.endsWith('no_catalog') },
]
const pointLabels: Record<string, string> = {
  fixed_cheapest: 'Cheapest paid', fixed_strongest: 'Strongest', rule_balanced: 'Rule-based',
  'learned:quality': 'quality', 'learned:cost': 'cost', 'learned:latency': 'fastest', 'learned:balanced': 'balanced',
}

function outcome(strategy: LearnedStrategyOutcome, view: string) {
  if (view === 'all') return strategy
  return strategy.by_task[view] ?? { prompts: 0, correct: 0, accuracy: 0, total_cost_usd: 0, median_latency_ms: null }
}

function points(strategies: LearnedStrategyOutcome[], view: string, axis: 'cost' | 'latency'): ScatterPoint[] {
  const spots = new Map<string, LearnedStrategyOutcome[]>()
  for (const strategy of strategies.filter((item) => pointLabels[item.strategy_id] && (view === 'all' || item.by_task[view]))) {
    const value = outcome(strategy, view)
    const key = `${value.correct}|${value.total_cost_usd.toFixed(6)}|${((value.median_latency_ms ?? 0) / 1000).toFixed(2)}`
    spots.set(key, [...(spots.get(key) ?? []), strategy])
  }
  const result: ScatterPoint[] = []
  for (const group of spots.values()) {
    const value = outcome(group[0], view)
    const learned = group.filter((item) => item.strategy_id.startsWith('learned:'))
    const fixed = group.filter((item) => !item.strategy_id.startsWith('learned:'))
    const router = learned.length === 4 ? 'Router (all)' : learned.length ? `Router: ${learned.map((item) => pointLabels[item.strategy_id]).join('/')}` : ''
    const label = [...fixed.map((item) => pointLabels[item.strategy_id]), router].filter(Boolean).join(' = ')
    const details = [`${value.correct} of ${value.prompts} right (${pct(value.accuracy)})`, `Cost ${usd(value.total_cost_usd)}`, `Median time ${seconds(value.median_latency_ms)}`]
    const kinds = [...new Set(group.map((item) => item.strategy_id.startsWith('learned:')))].sort()
    kinds.forEach((isLearned, index) => result.push({
      id: `${group[0].strategy_id}-${isLearned}`, label: index === kinds.length - 1 ? label : '', learned: isLearned,
      x: axis === 'cost' ? value.total_cost_usd : (value.median_latency_ms ?? 0) / 1000, y: value.accuracy * 100, details,
    }))
  }
  return result
}

function verdict(item: PairedComparison) {
  if (item.holm_p < 0.05) {
    return item.accuracy_difference > 0
      ? { tone: 'good' as const, text: 'More accurate' }
      : { tone: 'bad' as const, text: 'Less accurate' }
  }
  return { tone: 'neutral' as const, text: 'No detectable difference' }
}

function costLine(item: PairedComparison) {
  if (item.cost_ratio == null) return 'The comparison is free, so there is no cost ratio.'
  const ci = item.cost_ratio_ci
  if (ci && ci.high < 1) return `${Math.round((1 - item.cost_ratio) * 100)}% cheaper (95% interval ${Math.round((1 - ci.high) * 100)}–${Math.round((1 - ci.low) * 100)}%).`
  if (ci && ci.low > 1) return `${item.cost_ratio.toFixed(2)}× the cost.`
  return `Cost ratio ${item.cost_ratio.toFixed(2)}×, not clearly different.`
}

const signedSeconds = (ms: number) => `${ms > 0 ? '+' : ms < 0 ? '−' : '±'}${Math.abs(ms / 1000).toFixed(1)} s`

function timeLine(item: PairedComparison) {
  if (!/:(latency|balanced)$/.test(item.strategy_id)) return ''
  const ci = item.median_latency_difference_ci
  const verdict = ci.high < 0 ? 'faster' : ci.low > 0 ? 'slower' : 'not clearly different'
  return ` Median time ${signedSeconds(item.median_latency_difference_ms)} (95% interval ${signedSeconds(ci.low)} to ${signedSeconds(ci.high)}), ${verdict}.`
}

const familyRank = ['learned', 'fixed', 'rule', 'model_task_prior', 'learned_no_catalog', 'oracle']
const order = (id: string) => familyRank.indexOf(strategyFamily(id)) * 10 + (id.endsWith('no_catalog') ? 5 : 0)
  + Math.max(0, priorityOrder.indexOf(id.split(':')[1] as RoutingPriority))
const zero = (interval: { low: number; high: number } | undefined) => !interval || (interval.low === 0 && interval.high === 0)

function Leaderboard({ evaluation, view }: { evaluation: EvaluationSet; view: string }) {
  const [showReferences, setShowReferences] = useState(false)
  const spread = new Map(evaluation.uncertainty.map((item) => [item.strategy_id, item]))
  const names = new Map(evaluation.matrix.map((row) => [row.model_id, row.display_name]))
  const rows = [...evaluation.strategies, ...evaluation.oracle]
  return (
    <div className={ui.tableWrap}>
      <table className={ui.table} aria-label={`Leaderboard · ${views.find((item) => item.id === view)?.label}`}>
        <thead><tr><th>Strategy</th><th>Right answers</th><th>Paid cost</th><th>Median time</th><th>Mostly sent to</th></tr></thead>
        <tbody>
          {groups.map((group) => {
            const members = rows.filter((item) => group.match(item.strategy_id)).sort((a, b) => order(a.strategy_id) - order(b.strategy_id))
            if (!members.length) return null
            const folded = group.title === 'References' && !showReferences
            return [
              <tr key={group.title} className={styles.groupRow}><td colSpan={5}>
                <div className={styles.between}>
                  <span>{group.title}</span>
                  {group.title === 'References' && <button type="button" className={styles.chip} onClick={() => setShowReferences(!showReferences)}>{showReferences ? 'Hide' : `Show ${members.length}: per-task averages, no live check, hindsight`}</button>}
                </div>
              </td></tr>,
              ...(folded ? [] : members).map((item) => {
                const value = outcome(item, view)
                const interval = view === 'all' ? spread.get(item.strategy_id) : undefined
                const total = Object.values(item.selected_models).reduce((sum, n) => sum + n, 0)
                const top = Object.entries(item.selected_models).slice(0, 2)
                return (
                  <tr key={item.strategy_id}>
                    <td><span className={ui.cellTitle}>{strategyLabel(item.strategy_id)}</span></td>
                    <td>
                      <div className={styles.accCell}>
                        <span className={`${ui.num} ${ui.strong}`}>{value.correct}/{value.prompts}</span>
                        <Meter value={value.accuracy} color={strategyFamily(item.strategy_id) === 'learned' ? 'var(--series-1)' : 'var(--text-3)'} label={pct(value.accuracy)} />
                      </div>
                      {interval && <span className={ui.cellSub}>{span(interval.accuracy, (x) => pct(x, 0))}</span>}
                    </td>
                    <td><span className={ui.num}>{usd(value.total_cost_usd)}</span>{interval && !zero(interval.total_cost_usd) && <span className={ui.cellSub}>{span(interval.total_cost_usd, usd)}</span>}</td>
                    <td><span className={ui.num}>{seconds(value.median_latency_ms)}</span>{interval && <span className={ui.cellSub}>{span(interval.median_latency_ms, (x) => seconds(x))}</span>}</td>
                    <td>{view === 'all' && total ? top.map(([model, n]) => <span key={model} className={ui.cellSub} style={{ marginTop: 0 }}>{names.get(model) ?? model} · {Math.round((n / total) * 100)}%</span>) : <span className={ui.muted}>—</span>}</td>
                  </tr>
                )
              }),
            ]
          })}
        </tbody>
      </table>
    </div>
  )
}

export function ResearchPage() {
  const report = useFinalReport()
  const learned = useLearnedReport()
  const { query } = useRoute()
  const [evaluationId, setEvaluationId] = useState<EvaluationSet['evaluation_id']>('final')
  const [view, setView] = useState('all')
  const [preset, setPreset] = useState<RoutingPriority>('quality')
  const data = report.data
  const evaluation = evaluationOf(data, evaluationId) ?? data?.evaluations[0]
  const robustness = data?.robustness.find((item) => item.evaluation_id === evaluation?.evaluation_id)
  const present = new Set(Object.keys(evaluation?.strategies[0]?.by_task ?? {}))
  const activeView = view === 'all' || present.has(view) ? view : 'all'
  const section = query.get('section')

  useEffect(() => {
    if (section && data) document.getElementById(section)?.scrollIntoView()
  }, [section, data])

  if (report.isLoading) return <div style={{ paddingTop: '3rem' }}><Skeleton height={500} /></div>
  if (!data || !evaluation) {
    return (
      <>
        <PageHeader eyebrow={<><BookOpen size={15} />Research</>} title="Research" />
        <Empty icon={<BookOpen size={22} />} title="No evaluation report yet">Run <code>python -m app.learned.final_eval</code> to build it.</Empty>
      </>
    )
  }

  const analysis = evaluation.routing_errors.find((item) => item.strategy_id === `learned:${preset}`)
  const breakdown = analysis ? (activeView === 'all' ? analysis.overall : analysis.by_task[activeView]) : undefined
  const isDrift = (item: PairedComparison) => item.baseline_id.startsWith('learned_no_catalog')
  const comparisonGroups = [
    { title: 'The adaptive router against the alternatives', items: evaluation.comparisons.filter((item) => !isDrift(item)) },
    { title: 'What the live catalog check is worth', items: evaluation.comparisons.filter(isDrift) },
  ].filter((group) => group.items.length)
  const reachOf = (items: PairedComparison[]) =>
    Math.max(0.05, ...items.flatMap((item) => [item.accuracy_difference_ci.low, item.accuracy_difference_ci.high]).map(Math.abs)) * 1.1
  const sweep = robustness?.priority_sweep ?? []
  const label = evaluationLabel[evaluation.evaluation_id]
  const items = highlights(evaluation)

  return (
    <>
      <PageHeader
        eyebrow={<><BookOpen size={15} />Research</>}
        title="Does routing pay off?"
        description="The adaptive router was frozen, then tested against single models, a hand-written rule router, and a hindsight oracle on prompts it had never seen. Here is everything we measured, with the uncertainty attached."
      />
      <div className={styles.withNav}>
        <nav className={styles.sideNav} aria-label="Sections">
          {nav.map((item) => {
            const Icon = item.icon
            return <a key={item.id} href={`#/research?section=${item.id}`} onClick={(event) => { event.preventDefault(); document.getElementById(item.id)?.scrollIntoView({ behavior: 'smooth' }) }}><Icon size={15} />{item.label}</a>
          })}
        </nav>
        <div>
          <div className={styles.controls} style={{ paddingTop: '2.75rem' }}>
            <Segmented label="Prompt set" value={evaluation.evaluation_id} onChange={setEvaluationId}
              options={data.evaluations.map((item) => ({ id: item.evaluation_id, label: `${evaluationLabel[item.evaluation_id].title} · ${item.prompts}`, title: evaluationLabel[item.evaluation_id].about }))} />
            <Segmented label="Task" value={activeView} onChange={setView} options={views.filter((item) => item.id === 'all' || present.has(item.id))} />
          </div>
          <p className={styles.small} style={{ marginTop: '0.6rem' }}>{label.about}{evaluation.title.includes('provisional') ? ' Provisional: not every prompt has a result yet.' : ''}</p>

          <Section id="highlights" icon={<BookOpen size={18} />} title="Highlights" description={`The short version, on the ${label.title.toLowerCase()} (${evaluation.prompts} prompts).`}>
            <div className={styles.grid2}>
              {items.map((item) => (
                <div key={item.label} className={styles.highlight}><span>{item.label}</span><strong>{item.value}</strong><p>{item.text}</p></div>
              ))}
            </div>
          </Section>

          <Section id="leaderboard" icon={<ListOrdered size={18} />} title="Leaderboard" description="Every strategy answered the same prompts. Ranges are 95% intervals from resampling the prompts; overlapping ranges mean the difference may be chance.">
            <Leaderboard evaluation={evaluation} view={activeView} />
          </Section>

          <Section id="tradeoffs" icon={<BarChart3 size={18} />} title="Accuracy against cost and speed" description="Up and to the left is better. The router's four priorities trace a trade-off; the baselines sit at single points.">
            <div style={{ marginBottom: '0.75rem' }}>
              <Legend items={[{ name: 'Adaptive router', color: 'var(--series-1)' }, { name: 'Baselines', color: 'var(--series-2)', shape: 'square' }]} />
            </div>
            <div className={styles.grid2}>
              <ScatterChart title="Accuracy against paid cost" subtitle="Total billed for all prompts" points={points(evaluation.strategies, activeView, 'cost')} xLabel="Total paid cost (USD)" formatX={(value) => `$${value < 0.1 && value > 0 ? value.toFixed(3) : value.toFixed(2)}`} yLabel="Right answers" />
              <ScatterChart title="Accuracy against response time" subtitle="Median per prompt" points={points(evaluation.strategies, activeView, 'latency')} xLabel="Median response time (s)" formatX={(value) => `${Number(value.toFixed(1))} s`} yLabel="Right answers" />
            </div>
          </Section>

          <Section id="significance" icon={<Sigma size={18} />} title="Is the difference real?" description="Each question was fixed before the fresh results were read. Correctness uses McNemar's exact test on the prompts where only one side was right; p-values are Holm-adjusted for the number of questions.">
            <div className={styles.stack}>{comparisonGroups.map((group) => (
            <Card key={group.title} pad={false}>
              <div className={styles.verdictGroup}>{group.title}</div>
              {group.items.map((item) => {
                const reach = reachOf(group.items)
                const result = verdict(item)
                return (
                  <div key={`${item.strategy_id}-${item.baseline_id}`} className={styles.verdict}>
                    <div>
                      <strong>{item.question}</strong>
                      <small>{strategyLabel(item.strategy_id)} vs {strategyLabel(item.baseline_id).toLowerCase()} · {costLine(item)}{timeLine(item)}</small>
                    </div>
                    <div>
                      <IntervalRow low={item.accuracy_difference_ci.low} high={item.accuracy_difference_ci.high} value={item.accuracy_difference} min={-reach} max={reach}
                        label={`Accuracy difference ${signed(item.accuracy_difference, (x) => pct(x))}, 95% interval ${span(item.accuracy_difference_ci, (x) => pct(x))}`} />
                      <span className={ui.cellSub}>{signed(item.accuracy_difference, (x) => pct(x))} ({span(item.accuracy_difference_ci, (x) => signed(x, (y) => pct(y, 0)))})</span>
                    </div>
                    <div className={styles.verdictNumbers}>
                      <Badge tone={result.tone}>{result.text}</Badge>
                      <span>{item.correct} vs {item.baseline_correct} · p {pValue(item.holm_p)}</span>
                    </div>
                  </div>
                )
              })}
            </Card>
            ))}</div>
            <p className={styles.small} style={{ marginTop: '0.6rem' }}>The bar shows the accuracy difference with its 95% interval; the line is zero. "No detectable difference" means the data cannot tell the two apart, not that they are identical.</p>
          </Section>

          <Section id="errors" icon={<Search size={18} />} title="Where the router goes wrong" description="Each choice compared with what every model actually did on the same prompt."
            actions={<Segmented label="Priority" value={preset} onChange={setPreset} options={priorityOrder.map((id) => ({ id, label: priorityLabel[id] }))} />}>
            {breakdown && (
              <div className={styles.figures}>
                <Stat label="Right answers" value={`${breakdown.correct}/${breakdown.prompts}`} hint={`Hindsight best: ${breakdown.oracle_correct}`} />
                <Stat label="No model was right" value={breakdown.unavoidable} hint={`of ${breakdown.wrong} wrong answers`} />
                <Stat label="Too cheap (under-routed)" value={breakdown.under_routed} hint="Wrong, while a pricier model was right" />
                <Stat label="Too expensive (over-routed)" value={breakdown.over_routed} hint={`${breakdown.over_routed_dominated} where a cheaper, no slower model was right`} />
                <Stat label="Extra spent" value={usd(breakdown.over_routing_extra_cost_usd)} hint={`of ${usd(breakdown.total_cost_usd)} paid`} />
              </div>
            )}
            {analysis && analysis.examples.length > 0 && (
              <div className={styles.exampleGrid}>
                {analysis.examples.map((example) => (
                  <article key={`${example.kind}-${example.sample_id}`} className={styles.example}>
                    <div className={styles.between}>
                      <Badge tone={example.kind === 'good' ? 'good' : example.kind === 'under' ? 'bad' : 'warn'} dot>{{ good: 'Good call', under: 'Too cheap', over: 'Too expensive' }[example.kind]}</Badge>
                      <code className={ui.muted}>{example.sample_id}</code>
                    </div>
                    <blockquote>{example.prompt_excerpt}</blockquote>
                    <p>{example.explanation}</p>
                  </article>
                ))}
              </div>
            )}
          </Section>

          {robustness && (
            <Section id="robustness" icon={<FlaskConical size={18} />} title="When prices, speed, or providers change" description="The stored answers were replayed under each change. One router is told about the change (as the live catalog or call monitoring would tell it); the other keeps its old estimates. Nothing was retrained."
              actions={<Segmented label="Priority" value={preset} onChange={setPreset} options={priorityOrder.map((id) => ({ id, label: priorityLabel[id] }))} />}>
              <div className={ui.tableWrap}>
                <table className={ui.table} aria-label="Robustness scenarios">
                  <thead><tr><th>Change</th><th>Router, told</th><th>Router, old estimates</th><th>Choices changed</th><th>Hindsight best</th><th>Always strongest</th></tr></thead>
                  <tbody>{robustness.scenarios.map((scenario) => {
                    const pick = (id: string) => scenario.strategies.find((item) => item.strategy_id === id)
                    const told = pick(`learned:${preset}`)
                    const old = pick(`learned_frozen:${preset}`)
                    const oracle = pick(`oracle:${preset}`)
                    const strongest = pick('fixed_strongest')
                    return (
                      <tr key={scenario.scenario.scenario_id}>
                        <td className={styles.scenario}>
                          <div className={styles.row}><strong>{scenario.scenario.title}</strong><Badge tone={scenario.scenario.observed ? 'warn' : 'neutral'}>{scenario.scenario.observed ? 'Really happened' : 'What if'}</Badge></div>
                          <small>{scenario.scenario.description}</small>
                        </td>
                        <td>{told && <><span className={`${ui.num} ${ui.strong}`}>{told.correct}/{scenario.prompts}</span><span className={`${ui.cellSub} ${ui.nowrap}`}>{usd(told.total_cost_usd)} · {seconds(told.median_latency_ms)}</span></>}</td>
                        <td>{old && <><span className={ui.num}>{old.correct}/{scenario.prompts}</span><span className={`${ui.cellSub} ${ui.nowrap}`}>{usd(old.total_cost_usd)} · {seconds(old.median_latency_ms)}</span></>}</td>
                        <td className={ui.num}>{told?.changed_decisions ?? '—'}</td>
                        <td className={ui.num}>{oracle?.correct ?? '—'}</td>
                        <td>{strongest && <><span className={ui.num}>{strongest.correct}</span><span className={ui.cellSub}>{usd(strongest.total_cost_usd)}</span></>}</td>
                      </tr>
                    )
                  })}</tbody>
                </table>
              </div>
              <p className={styles.small} style={{ marginTop: '0.6rem' }}>Injected failures return an error after 2 seconds. Choices changed counts prompts routed differently from the unchanged conditions.</p>
            </Section>
          )}

          {sweep.length > 0 && (
            <Section id="priorities" icon={<SlidersHorizontal size={18} />} title="What your priority costs you" description="The router with accuracy weighted 1 and one other weight turned up step by step, from 0 to 5. Each point is one setting; hover for details.">
              <div className={styles.grid2}>
                {(['cost', 'latency'] as const).map((axis) => {
                  const series = sweep.filter((point) => point.axis === axis)
                  return (
                    <PathChart key={axis}
                      title={axis === 'cost' ? 'Turning up the cost weight' : 'Turning up the speed weight'}
                      subtitle={axis === 'cost' ? 'Accuracy against total paid cost' : 'Accuracy against median response time'}
                      xLabel={axis === 'cost' ? 'Total paid cost (USD)' : 'Median response time (s)'} yLabel="Share right"
                      formatX={axis === 'cost' ? (x) => `$${x.toFixed(2)}` : (x) => `${x.toFixed(0)} s`} formatY={(y) => pct(y, 0)}
                      points={series.map((point, index) => ({
                        x: axis === 'cost' ? point.total_cost_usd : (point.median_latency_ms ?? 0) / 1000,
                        y: point.accuracy,
                        label: index === 0 ? `weight 0` : index === series.length - 1 ? `weight ${point.weight}` : undefined,
                        detail: [`${axis === 'cost' ? 'Cost' : 'Speed'} weight ${point.weight}`, `${point.correct} of ${robustness?.prompts} right`, `${usd(point.total_cost_usd)} · median ${seconds(point.median_latency_ms)}`],
                      }))}
                    />
                  )
                })}
              </div>
            </Section>
          )}

          {learned.data && (
            <Section id="training" icon={<GraduationCap size={18} />} title="How the router was built" description="Two classifiers were trained to predict whether a model answers a prompt correctly. The better one on held-out validation prompts became the router, and each priority's weights were tuned on the same validation prompts.">
              <div className={styles.grid4} style={{ marginBottom: '1rem' }}>
                <Stat label="Training rows" value={(learned.data.rows.train + learned.data.rows.validation).toLocaleString()} hint="Prompt × model outcomes, train + validation" />
                <Stat label="Features" value={learned.data.features.length} hint="Prompt shape, task, model identity, price, history" />
                <Stat label="Selected" value="Logistic regression" hint="Lower log loss on the validation prompts" />
                <Stat label="Validation log loss" value={Math.min(...Object.values(learned.data.classifiers).map((item) => item.validation.log_loss)).toFixed(3)} hint={`Per-task averages alone: ${learned.data.reference_model_task_prior.log_loss.toFixed(3)}`} />
              </div>
              <div className={styles.grid2}>
                <div className={ui.tableWrap}>
                  <table className={ui.table} aria-label="Classifier comparison">
                    <thead><tr><th>Predictor</th><th>Log loss</th><th>AUC</th><th>Overfit gap</th></tr></thead>
                    <tbody>
                      {Object.entries(learned.data.classifiers).map(([id, entry]) => (
                        <tr key={id} className={id === learned.data!.selected_family ? ui.selectedRow : undefined}>
                          <td><span className={ui.cellTitle}>{id === 'logistic_regression' ? 'Logistic regression' : 'Gradient-boosted trees'}</span><span className={ui.cellSub}>{Object.entries(entry.best_params).map(([key, value]) => `${key.replace('logisticregression__', '')} ${value}`).join(' · ')}</span></td>
                          <td className={ui.num}>{entry.validation.log_loss.toFixed(3)}</td>
                          <td className={ui.num}>{entry.validation.roc_auc?.toFixed(3) ?? '—'}</td>
                          <td className={ui.num}>{entry.overfit_gap_log_loss.toFixed(3)}</td>
                        </tr>
                      ))}
                      <tr><td><span className={ui.cellTitle}>Per-task averages only</span><span className={ui.cellSub}>No prompt features</span></td><td className={ui.num}>{learned.data.reference_model_task_prior.log_loss.toFixed(3)}</td><td className={ui.num}>{learned.data.reference_model_task_prior.roc_auc?.toFixed(3) ?? '—'}</td><td className={ui.num}>—</td></tr>
                    </tbody>
                  </table>
                </div>
                <div className={ui.tableWrap}>
                  <table className={ui.table} aria-label="Tuned weights">
                    <thead><tr><th>Priority</th><th>Cost</th><th>Speed</th><th>Right on validation</th></tr></thead>
                    <tbody>{priorityOrder.map((priority) => {
                      const item = learned.data!.weight_tuning.find((entry) => entry.priority === priority)
                      return item && (
                        <tr key={priority}>
                          <td className={ui.strong}>{priorityLabel[priority]}</td>
                          <td className={ui.num}>{item.weights.cost}</td>
                          <td className={ui.num}>{item.weights.latency}</td>
                          <td className={ui.num}>{item.validation_correct}/{learned.data!.validation_prompts}</td>
                        </tr>
                      )
                    })}</tbody>
                  </table>
                </div>
              </div>
              <p className={styles.small} style={{ marginTop: '0.6rem' }}>Lower log loss is better. Per-task averages predict about as well as the full model: on these benchmarks, which model to use depends mostly on the task, not on the details of the prompt.</p>
            </Section>
          )}

          <Section id="method" icon={<Scale size={18} />} title="Method and limits" description="What was measured, and what the numbers do not show.">
            <div className={styles.grid2}>
              <Card>
                <div className={styles.body}>
                  <p><strong>Prompts.</strong> 900 questions from four public benchmarks: GSM8K (grade-school math), MMLU-Pro (multiple-choice knowledge across 14 subjects), and HumanEval+ and MBPP+ (Python functions). 600 built and tested the router; 300 fresh ones were drawn only after it was frozen.</p>
                  <p><strong>Grading.</strong> Math answers must match exactly, multiple-choice letters must match, and code must pass every hidden test, run in a sandbox with no network. A failed call counts as wrong.</p>
                  <p><strong>Calls.</strong> Temperature 0, the same token limits for every model, one retry on a timeout, rate limit, or server error. Costs are what the providers billed.</p>
                  <p><strong>Statistics.</strong> 95% intervals from 10,000 bootstrap resamples of the prompts; paired tests fixed in advance, with Holm's correction.</p>
                </div>
              </Card>
              <Card>
                <ul className={styles.limits}>
                  <li><AlertTriangle size={15} />Benchmarks are not your traffic. Real prompts are longer and messier, and "right" is rarely a single number.</li>
                  <li><AlertTriangle size={15} />Cost and time are scored relative to the most expensive and the slowest model available. When that model gets pricier or slower, the others look better by comparison, so a change to one model can move choices among the rest: telling the router that the free OVHcloud models had become three times slower made its Fastest priority slower, not faster.</li>
                  <li><AlertTriangle size={15} />The tuned priorities give reliability no weight, so a model that starts failing is avoided only if you raise the reliability weight.</li>
                  <li><AlertTriangle size={15} />The router knows only the nine models it was trained with; a new model needs measured answers before it can be chosen.</li>
                  <li><AlertTriangle size={15} />With a few hundred prompts, differences of a few answers are within noise. Read the intervals.</li>
                </ul>
              </Card>
            </div>
          </Section>

          <Section id="downloads" icon={<Download size={18} />} title="Download the data" description="Everything above, as CSV or JSON. Built from the published files only: no model responses, no request IDs, no keys.">
            <div className={styles.downloads}>
              {exportTables.map((table) => (
                <div key={table.id} className={styles.download}>
                  <div><strong>{table.label}</strong><span>{table.about}</span></div>
                  <a href={client.exportUrl(table.id, 'csv')} download><Download size={14} />CSV</a>
                  <a href={client.exportUrl(table.id, 'json')} download><Download size={14} />JSON</a>
                </div>
              ))}
            </div>
            <p className={styles.small} style={{ marginTop: '0.75rem' }}><Gauge size={13} style={{ verticalAlign: '-2px' }} /> Router file SHA-256 <code>{data.artifact_sha256.slice(0, 12)}…</code> · fresh prompt set SHA-256 <code>{data.final_set_sha256.slice(0, 12)}…</code> · fresh-set calls billed {usd(data.spend_usd)}</p>
          </Section>
        </div>
      </div>
    </>
  )
}
