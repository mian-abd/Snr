import { useQuery } from '@tanstack/react-query'
import { BrainCircuit, ShieldCheck } from 'lucide-react'
import { client } from '../api/client'
import type { ClassifierMetrics } from '../api/types'
import styles from './Panels.module.css'

const tasks = [
  { id: 'math', label: 'GSM8K' },
  { id: 'qa', label: 'MMLU-Pro' },
  { id: 'code', label: 'HumanEval+ · MBPP+' },
]
const access: Record<string, string> = { paid: 'Paid', free: 'Free', local: 'Local' }
const families: Record<string, string> = {
  logistic_regression: 'Logistic regression',
  gradient_boosted_trees: 'Gradient-boosted trees',
  model_task_prior: 'Reference: model × task rate',
}
const fixed: Record<string, string> = {
  fixed_cheapest: 'Always cheapest paid',
  fixed_strongest: 'Always strongest',
  rule_balanced: 'Checkpoint 2 rule router',
}
const priorities: Record<string, string> = { balanced: 'balanced', cost: 'lower cost', quality: 'higher quality', latency: 'faster response' }
const params: Record<string, string> = { logisticregression__C: 'C', max_depth: 'depth', learning_rate: 'rate', max_iter: 'iterations' }

const seconds = (value: number | null) => (value == null ? '—' : `${(value / 1000).toFixed(1)} s`)
const usd = (value: number) => `$${value.toFixed(3)}`
const metric = (value: number | null) => (value == null ? '—' : value.toFixed(3))
const number = `${styles.mono} ${styles.nowrap}`
const strong = `${styles.metricStrong} ${styles.nowrap}`

function strategyLabel(id: string) {
  if (fixed[id]) return fixed[id]
  const [family, priority] = id.split(':')
  return `${families[family] ?? family} · ${priorities[priority] ?? priority}`
}

export function LearnedPanel() {
  const report = useQuery({ queryKey: ['learned-report'], queryFn: client.learnedReport })
  const data = report.data
  const names = new Map(data?.matrix.map((row) => [row.model_id, row.display_name]))
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

  return (
    <section className={styles.panel} aria-labelledby="learned-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>05 / LEARNED ROUTER</span>
          <h2 id="learned-heading">Learning from measured outcomes.</h2>
          <p>Two lightweight classifiers predict whether each model answers each prompt correctly. They train on the training split of a fixed 600-prompt suite and are compared on the validation split. This view is read-only: live routing still uses the rule policy.</p>
        </div>
      </div>
      {report.isError && <p className={styles.errorBox}>The learned-router report could not be loaded.</p>}
      {data === null && <div className={styles.emptyState}><BrainCircuit size={20} /><span>No learned-router report yet. Run <code>python -m app.learned.train</code>.</span></div>}
      {data && <>
        <div className={styles.protocolStrip}>
          {['600 prompts', 'GSM8K · MMLU-Pro · HumanEval+ · MBPP+', `${data.matrix.length} models`, `${data.matrix.reduce((sum, row) => sum + row.prompts, 0).toLocaleString()} cells`, 'split 60 / 20 / 20', 'test split held out', 'temperature 0'].map((label) => <span key={label}>{label}</span>)}
        </div>

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
                  <td><strong>{families[item.id] ?? item.id}</strong></td>
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
          <p className={styles.disclaimer}>Lower log loss and Brier are better. Each family&apos;s setting is chosen by validation log loss; the gap is validation minus training log loss.</p>
        </section>

        <section className={styles.dashboard} aria-labelledby="replay-heading">
          <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>Routing replay · {data.validation_prompts} validation prompts</span><h3 id="replay-heading">Which model each strategy would pick.</h3></div></div>
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
          <p className={styles.disclaimer}>{data.note} Each prompt is scored by the chosen model&apos;s saved outcome. With {data.validation_prompts} prompts, differences of one to three correct answers are within noise. Paid answers cut off at the token cap were recorded at $0 before 2026-10-28, so paid costs are slightly low.</p>
        </section>
      </>}
    </section>
  )
}
