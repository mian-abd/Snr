import { useQuery } from '@tanstack/react-query'
import { BrainCircuit, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { ClassifierMetrics, LearnedStrategyOutcome, RoutingPriority, RoutingWeights } from '../api/types'
import { LearnedRouterForm } from './LearnedRouterForm'
import styles from './Panels.module.css'
import { ScatterChart, type ScatterPoint } from './ScatterChart'

const tasks = [
  { id: 'math', label: 'GSM8K' },
  { id: 'qa', label: 'MMLU-Pro' },
  { id: 'code', label: 'HumanEval+ · MBPP+' },
]
const views = [{ id: 'all', label: 'All prompts' }, ...tasks]
const access: Record<string, string> = { paid: 'Paid', free: 'Free', local: 'Local' }
const families: Record<string, string> = {
  logistic_regression: 'Logistic regression',
  logistic_regression_tuned: 'Logistic regression, tuned',
  gradient_boosted_trees: 'Gradient-boosted trees',
  model_task_prior: 'Reference: model × task rate',
  learned: 'Learned router',
}
const fixed: Record<string, string> = {
  fixed_cheapest: 'Always cheapest paid',
  fixed_strongest: 'Always strongest',
  rule_balanced: 'Checkpoint 2 rule router',
}
const priorities: Record<string, string> = { balanced: 'balanced', cost: 'lower cost', quality: 'higher quality', latency: 'faster response' }
const pointLabels: Record<string, string> = {
  fixed_cheapest: 'Always cheapest', fixed_strongest: 'Always strongest', rule_balanced: 'CP2 rule router',
  'learned:quality': 'quality', 'learned:cost': 'cost', 'learned:latency': 'faster', 'learned:balanced': 'balanced',
}
const params: Record<string, string> = { logisticregression__C: 'C', max_depth: 'depth', learning_rate: 'rate', max_iter: 'iterations' }

const seconds = (value: number | null) => (value == null ? '—' : `${(value / 1000).toFixed(1)} s`)
const usd = (value: number) => `$${value.toFixed(value > 0 && value < 0.01 ? 4 : 3)}`
const metric = (value: number | null) => (value == null ? '—' : value.toFixed(3))
const number = `${styles.mono} ${styles.nowrap}`
const strong = `${styles.metricStrong} ${styles.nowrap}`

function strategyLabel(id: string) {
  if (fixed[id]) return fixed[id]
  const [family, priority] = id.split(':')
  return `${families[family] ?? family} · ${priorities[priority] ?? priority}`
}

function outcome(strategy: LearnedStrategyOutcome, view: string) {
  if (view === 'all') return strategy
  const task = strategy.by_task[view]
  return { ...task, cost_per_correct_usd: task.correct ? task.total_cost_usd / task.correct : null, p95_latency_ms: null }
}

function chartPoints(strategies: LearnedStrategyOutcome[], view: string, axis: 'cost' | 'latency'): ScatterPoint[] {
  const spots = new Map<string, LearnedStrategyOutcome[]>()
  for (const strategy of strategies.filter((item) => pointLabels[item.strategy_id])) {
    const value = outcome(strategy, view)
    const key = `${value.correct}|${value.total_cost_usd.toFixed(6)}|${((value.median_latency_ms ?? 0) / 1000).toFixed(2)}`
    spots.set(key, [...(spots.get(key) ?? []), strategy])
  }
  const points: ScatterPoint[] = []
  for (const group of spots.values()) {
    const value = outcome(group[0], view)
    const baselines = group.filter((item) => !item.strategy_id.startsWith('learned:')).map((item) => pointLabels[item.strategy_id])
    const learned = group.filter((item) => item.strategy_id.startsWith('learned:')).map((item) => pointLabels[item.strategy_id])
    const label = [...baselines, ...(learned.length ? [`Learned · ${learned.join(', ')}`] : [])].join(' = ')
    const details = [`${value.correct} of ${value.prompts} correct (${(value.accuracy * 100).toFixed(1)}%)`, `Cost ${usd(value.total_cost_usd)}`, `Median latency ${seconds(value.median_latency_ms)}`]
    const kinds = [...new Set(group.map((item) => item.strategy_id.startsWith('learned:')))].sort()
    kinds.forEach((isLearned, index) => points.push({
      id: `${group[0].strategy_id}-${isLearned}`, label: index === kinds.length - 1 ? label : '', learned: isLearned,
      x: axis === 'cost' ? value.total_cost_usd : (value.median_latency_ms ?? 0) / 1000, y: value.accuracy * 100, details,
    }))
  }
  return points
}

export function LearnedPanel() {
  const report = useQuery({ queryKey: ['learned-report'], queryFn: client.learnedReport })
  const [view, setView] = useState('all')
  const data = report.data
  const names = new Map(data?.matrix.map((row) => [row.model_id, row.display_name]))
  const presets: Partial<Record<RoutingPriority, RoutingWeights>> = Object.fromEntries(data?.weight_tuning.map((item) => [item.priority, item.weights]) ?? [])
  const predictors: Array<{ id: string; setting: string; validation: ClassifierMetrics; gap: number | null }> = data
    ? [
        ...Object.entries(data.classifiers).map(([id, entry]) => ({
          id,
          setting: Object.entries(entry.best_params).map(([key, value]) => `${params[key] ?? key} ${value}`).join(' · '),
          validation: entry.validation,
          gap: entry.overfit_gap_log_loss,
        })),
        { id: 'model_task_prior', setting: 'none', validation: data.reference_model_task_prior, gap: null },
      ]
    : []
  const best = predictors.length ? predictors.reduce((winner, item) => (item.validation.log_loss < winner.validation.log_loss ? item : winner)).id : null
  const learnedBest = Math.min(...Object.values(data?.classifiers ?? {}).map((entry) => entry.validation.log_loss))
  const held = data?.heldout
  const find = (id: string) => held?.strategies.find((item) => item.strategy_id === id)
  const [lq, fs, lc, fc] = ['learned:quality', 'fixed_strongest', 'learned:cost', 'fixed_cheapest'].map(find)
  const viewLabel = views.find((item) => item.id === view)?.label ?? view

  return (
    <section className={styles.panel} aria-labelledby="learned-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>05 / LEARNED ROUTER</span>
          <h2 id="learned-heading">Learned from measured outcomes.</h2>
          <p>Logistic regression predicts whether each model answers a prompt correctly, and multi-objective scoring weighs that against expected cost, latency, and failures under the chosen priority. It was selected on the validation split, refit on training and validation data, and tested once on held-out prompts.</p>
        </div>
      </div>
      {report.isError && <p className={styles.errorBox}>The learned-router report could not be loaded.</p>}
      {data === null && <div className={styles.emptyState}><BrainCircuit size={20} /><span>No learned-router report yet. Run <code>python -m app.learned.train</code>.</span></div>}
      {data && held && <>
        <div className={styles.protocolStrip}>
          {['600 prompts', 'GSM8K · MMLU-Pro · HumanEval+ · MBPP+', `${data.matrix.length} models`, `${data.matrix.reduce((sum, row) => sum + row.prompts, 0).toLocaleString()} cells`, 'split 60 / 20 / 20', `selected: ${families[data.selected_family] ?? data.selected_family}`, 'temperature 0'].map((label) => <span key={label}>{label}</span>)}
        </div>

        <LearnedRouterForm presets={presets} />

        <section className={styles.dashboard} aria-labelledby="heldout-heading">
          <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>Checkpoint 3 comparison · held-out test split · {held.prompts} prompts</span><h3 id="heldout-heading">The learned router against the baselines, on prompts it never saw.</h3></div></div>
          {lq && fs && <div className={styles.proofLine}><ShieldCheck size={16} />Higher-quality preset: {lq.correct} of {lq.prompts} correct for {usd(lq.total_cost_usd)}; always strongest: {fs.correct} for {usd(fs.total_cost_usd)}.</div>}
          {lc && fc && <div className={styles.proofLine}><ShieldCheck size={16} />Lower-cost preset: {lc.correct} correct for {usd(lc.total_cost_usd)}; always cheapest paid: {fc.correct} for {usd(fc.total_cost_usd)}, with a median latency of {seconds(lc.median_latency_ms)} against {seconds(fc.median_latency_ms)}.</div>}
          <div className={styles.segmented} role="group" aria-label="Task filter for the held-out comparison">
            {views.map((item) => <button key={item.id} type="button" aria-pressed={view === item.id} onClick={() => setView(item.id)}>{item.label}</button>)}
          </div>
          <div className={styles.chartLegend}><span><i className={styles.swatchLearned} />Learned router</span><span><i className={styles.swatchBaseline} />Baselines</span></div>
          <div className={styles.chartPair}>
            <ScatterChart title={`Accuracy against cost · ${viewLabel}`} points={chartPoints(held.strategies, view, 'cost')} xLabel="Total paid cost (USD)" formatX={(value) => `$${value < 0.1 && value > 0 ? value.toFixed(3) : value.toFixed(2)}`} />
            <ScatterChart title={`Accuracy against response time · ${viewLabel}`} points={chartPoints(held.strategies, view, 'latency')} xLabel="Median latency (seconds)" formatX={(value) => `${Number(value.toFixed(1))} s`} />
          </div>
          <div className={styles.tableWrap}>
            <table aria-label={`Held-out comparison · ${viewLabel}`}>
              <thead><tr><th>Strategy</th><th>Correct</th><th>Cost</th><th>Cost per correct</th><th>Median latency</th><th>p95 latency</th><th>Models picked</th></tr></thead>
              <tbody>{held.strategies.map((item) => {
                const value = outcome(item, view)
                return (
                  <tr key={item.strategy_id}>
                    <td><strong>{strategyLabel(item.strategy_id)}</strong></td>
                    <td className={strong}>{value.correct} / {value.prompts}</td>
                    <td className={number}>{usd(value.total_cost_usd)}</td>
                    <td className={number}>{value.cost_per_correct_usd == null ? '—' : `$${value.cost_per_correct_usd.toFixed(5)}`}</td>
                    <td className={number}>{seconds(value.median_latency_ms)}</td>
                    <td className={number}>{seconds(value.p95_latency_ms)}</td>
                    <td className={styles.mono}>{view === 'all' ? Object.entries(item.selected_models).map(([model, count]) => `${names.get(model) ?? model} × ${count}`).join(', ') : '—'}</td>
                  </tr>
                )
              })}</tbody>
            </table>
          </div>
          <p className={styles.disclaimer}>Read once, after selection and tuning; nothing was changed afterwards. Held-out log loss: learned router {metric(held.classifier.log_loss)}, model × task reference {metric(held.reference_model_task_prior.log_loss)}. Outcomes are replayed from the saved matrix, so no model was called again. Per-task views have no p95 or model counts. With {held.prompts} prompts, a difference of one to three correct answers is within noise.</p>
        </section>

        {(held.oracle ?? []).length > 0 && (
          <section className={styles.dashboard} aria-labelledby="oracle-heading">
            <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>Oracle gap and routing errors · held-out test split</span><h3 id="oracle-heading">How far each priority is from perfect hindsight.</h3></div></div>
            <div className={styles.tableWrap}>
              <table aria-label="Oracle gap and routing errors">
                <thead><tr><th>Priority</th><th>Learned correct</th><th>Oracle correct</th><th>Learned cost</th><th>Oracle cost</th><th>Wrong answers</th><th>Under-routed</th><th>Over-routed</th></tr></thead>
                <tbody>{held.routing_errors.map((errors) => {
                  const priority = errors.strategy_id.split(':')[1]
                  const learned = find(errors.strategy_id)
                  const oracle = held.oracle.find((item) => item.strategy_id === `oracle:${priority}`)
                  return (
                    <tr key={errors.strategy_id}>
                      <td><strong>{priorities[priority] ?? priority}</strong></td>
                      <td className={strong}>{learned ? `${learned.correct} / ${learned.prompts}` : '—'}</td>
                      <td className={number}>{oracle ? `${oracle.correct} / ${oracle.prompts}` : '—'}</td>
                      <td className={number}>{learned ? usd(learned.total_cost_usd) : '—'}</td>
                      <td className={number}>{oracle ? usd(oracle.total_cost_usd) : '—'}</td>
                      <td className={number}>{errors.wrong}</td>
                      <td className={number}>{errors.under_routed}</td>
                      <td className={number}>{errors.over_routed}</td>
                    </tr>
                  )
                })}</tbody>
              </table>
            </div>
            <p className={styles.disclaimer}>The oracle scores each prompt with the same weights but the observed outcome, so it is not deployable; it bounds what any router could reach. Under-routed: the chosen model failed while a model with a higher expected cost succeeded. Over-routed: the chosen model succeeded but a model with a lower expected cost also did. Free models count as cheapest, so any paid choice that a free model could have matched counts as over-routing, even when the free model is much slower.</p>
          </section>
        )}

        <section className={styles.dashboard} aria-labelledby="tuning-heading">
          <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>User weights · tuned on the validation split</span><h3 id="tuning-heading">One weight preset per priority.</h3></div></div>
          <div className={styles.tableWrap}>
            <table>
              <thead><tr><th>Priority</th><th>Cost</th><th>Latency</th><th>Reliability</th><th>Validation correct</th><th>Accuracy floor</th><th>Validation cost</th><th>Median latency</th></tr></thead>
              <tbody>{data.weight_tuning.map((item) => (
                <tr key={item.priority}>
                  <td><strong>{priorities[item.priority]}</strong></td>
                  <td className={number}>{item.weights.cost}</td>
                  <td className={number}>{item.weights.latency}</td>
                  <td className={number}>{item.weights.reliability}</td>
                  <td className={strong}>{item.validation_correct} / {data.validation_prompts}</td>
                  <td className={number}>{item.accuracy_floor ?? 'best'}</td>
                  <td className={number}>{usd(item.validation_cost_usd)}</td>
                  <td className={number}>{seconds(item.validation_median_latency_ms)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className={styles.disclaimer}>Quality weight 1. Higher quality maximizes correct answers. Lower cost and faster response are the cheapest and fastest weights that answer at least as many prompts as always using the cheapest paid model. Balanced clears the halfway mark and minimizes the shortfall, cost, and latency together.</p>
        </section>

        <section className={styles.dashboard} aria-labelledby="matrix-heading">
          <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>Benchmark matrix · run {data.run_id}</span><h3 id="matrix-heading">Every model, every prompt.</h3></div></div>
          <div className={styles.tableWrap}>
            <table>
              <thead><tr><th>Model</th><th>Access</th>{tasks.map((task) => <th key={task.id}>{task.label}</th>)}<th>Total</th><th>Median latency</th><th>Paid cost</th><th>Failed calls</th></tr></thead>
              <tbody>{data.matrix.map((row) => (
                <tr key={row.model_id}>
                  <td><strong>{row.display_name}</strong><code>{row.model_id}</code></td>
                  <td>{access[row.access] ?? row.access}</td>
                  {tasks.map((task) => <td key={task.id} className={number}>{row.correct_by_task[task.id] ?? 0} / {row.prompts_by_task[task.id] ?? 0}</td>)}
                  <td className={strong}>{row.correct} / {row.prompts}</td>
                  <td className={number}>{seconds(row.median_latency_ms)}</td>
                  <td className={number}>{row.access === 'paid' ? usd(row.cost_usd) : 'Free'}</td>
                  <td className={number}>{row.failed_calls}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className={styles.disclaimer}>Code passes only when the base and extra EvalPlus tests both pass, scored in a Docker container with no network. Every failed call counts as wrong.{data.models_without_results.length > 0 && <> Not in this matrix: {data.models_without_results.map((id, index) => <span key={id}>{index > 0 && ', '}<code>{id}</code></span>)} (their free services were overloaded when tested).</>}</p>
        </section>

        <section className={styles.dashboard} aria-labelledby="classifier-heading">
          <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>Classifier comparison · validation split</span><h3 id="classifier-heading">Logistic regression against boosted trees.</h3></div></div>
          <div className={styles.tableWrap}>
            <table>
              <thead><tr><th>Predictor</th><th>Chosen setting</th><th>Log loss</th><th>Brier</th><th>ROC AUC</th><th>Overfitting gap</th></tr></thead>
              <tbody>{predictors.map((item) => (
                <tr key={item.id} className={item.id === best ? styles.selectedRow : undefined}>
                  <td><strong>{families[item.id] ?? item.id}</strong>{item.id === data.selected_family && <code>selected for the router</code>}</td>
                  <td className={styles.mono}>{item.setting}</td>
                  <td className={item.id === best ? styles.metricStrong : styles.mono}>{metric(item.validation.log_loss)}</td>
                  <td className={styles.mono}>{metric(item.validation.brier)}</td>
                  <td className={styles.mono}>{metric(item.validation.roc_auc)}</td>
                  <td className={styles.mono}>{metric(item.gap)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className={styles.proofLine}><ShieldCheck size={16} />
            {data.reference_model_task_prior.log_loss <= learnedBest
              ? `Each model's training success rate per task predicts as well as either classifier, so on ${(data.rows.train / data.matrix.length).toLocaleString()} training prompts the prompt features add no signal yet.`
              : `The best classifier beats the model × task reference by ${(data.reference_model_task_prior.log_loss - learnedBest).toFixed(3)} log loss.`}
          </div>
          <p className={styles.disclaimer}>{data.selection_rule} Lower log loss and Brier are better; the gap is validation minus training log loss.</p>
        </section>

        <details className={styles.details}>
          <summary>Validation routing replay · {data.validation_prompts} prompts · {data.strategies.length} strategies</summary>
          <div className={styles.tableWrap}>
            <table>
              <thead><tr><th>Strategy</th><th>Correct</th><th>Cost</th><th>Median latency</th><th>p95 latency</th><th>Models picked</th></tr></thead>
              <tbody>{data.strategies.map((item) => (
                <tr key={item.strategy_id}>
                  <td><strong>{strategyLabel(item.strategy_id)}</strong></td>
                  <td className={strong}>{item.correct} / {item.prompts}</td>
                  <td className={number}>{usd(item.total_cost_usd)}</td>
                  <td className={number}>{seconds(item.median_latency_ms)}</td>
                  <td className={number}>{seconds(item.p95_latency_ms)}</td>
                  <td className={styles.mono}>{Object.entries(item.selected_models).map(([model, count]) => `${names.get(model) ?? model} × ${count}`).join(', ')}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className={styles.disclaimer}>Untuned rows use the starting presets; “tuned” rows use the presets above. Paid answers cut off at the token cap were recorded at $0 before 2026-10-28, so paid costs are slightly low.</p>
        </details>
      </>}
    </section>
  )
}
