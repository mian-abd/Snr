import { Wrench } from 'lucide-react'
import { useState } from 'react'
import type { EvidenceRow, RoutingPriority, ScenarioStrategy, ScoringFixEvaluation, ScoringFixReport } from '../api/types'
import { Dumbbell, type DumbbellRow } from '../charts/Dumbbell'
import { dollarTick, linearScale, logScale } from '../charts/scales'
import { priorityLabel } from '../lib/data'
import { seconds, usdOrFree } from '../lib/format'
import { Badge, ChartCard, Notice, Section, Segmented } from '../ui'
import explorers from '../charts/explorers.module.css'
import ui from '../ui/ui.module.css'
import styles from './pages.module.css'

type Measure = 'accuracy' | 'time' | 'cost'

const routerName = { frozen: 'Frozen scoring', fixed: 'Fixed scoring' } as const
const MERCURY = 'observed_drift'
const GEMMA = 'gemma_mercury_unavailable'
const priorities: RoutingPriority[] = ['quality', 'cost', 'latency']

const summary = (item: ScenarioStrategy, prompts: number) => `${item.correct}/${prompts} right · ${usdOrFree(item.total_cost_usd)} · ${seconds(item.median_latency_ms)}`

function scenarioTitle(evaluation: ScoringFixEvaluation, id: string) {
  return evaluation.fixed.scenarios.find((item) => item.scenario.scenario_id === id)?.scenario.title ?? id
}

/** The evidence of every question for one prompt set, one row per scenario, priority and router. */
function evidenceRows(report: ScoringFixReport, evaluationId: string) {
  const seen = new Set<string>()
  const rows: EvidenceRow[] = []
  for (const question of report.questions) {
    for (const row of question.evidence) {
      const key = `${row.scenario_id}:${row.priority}:${row.router}`
      if (row.evaluation_id !== evaluationId || seen.has(key)) continue
      seen.add(key)
      rows.push(row)
    }
  }
  return rows
}

function FixChart({ evaluation, rows }: { evaluation: ScoringFixEvaluation; rows: EvidenceRow[] }) {
  const [measure, setMeasure] = useState<Measure>('accuracy')
  const prompts = evaluation.prompts
  const value = (item: ScenarioStrategy) => (measure === 'accuracy' ? (item.correct / prompts) * 100 : measure === 'time' ? (item.median_latency_ms ?? 0) / 1000 : item.total_cost_usd)
  const dumbbells: DumbbellRow[] = rows.map((row) => {
    const label = `${scenarioTitle(evaluation, row.scenario_id)} · ${priorityLabel[row.priority]} · ${routerName[row.router]}`
    const diff = value(row.told) - value(row.old)
    const same = Math.abs(diff) < (measure === 'cost' ? 0.00005 : measure === 'time' ? 0.05 : 0.05)
    const text = same ? 'Same' : measure === 'accuracy' ? `${diff > 0 ? '+' : '−'}${Math.abs(row.told.correct - row.old.correct)} right` : measure === 'time' ? `${diff > 0 ? '+' : '−'}${Math.abs(diff).toFixed(1)} s` : `${diff > 0 ? '+' : '−'}$${Math.abs(diff).toFixed(4)}`
    return {
      id: `${row.scenario_id}:${row.priority}:${row.router}`,
      label,
      a: value(row.told),
      b: value(row.old),
      delta: { text, tone: same ? 'same' : measure === 'accuracy' ? (diff > 0 ? 'good' : 'bad') : 'plain' },
      details: [label, `Told: ${summary(row.told, prompts)}`, `Old estimates: ${summary(row.old, prompts)}`, `Nothing changed: ${summary(row.unchanged, prompts)}`],
      summary: `${label}. Told: ${summary(row.told, prompts)}. Old estimates: ${summary(row.old, prompts)}.`,
    }
  })
  const values = dumbbells.flatMap((row) => [row.a, row.b])
  const scale = measure === 'accuracy'
    ? linearScale(values, { format: (v) => `${Math.round(v)}%`, minSpan: 10, floor: 0, ceil: 100 })
    : measure === 'time'
      ? linearScale(values, { format: (v) => `${v.toFixed(0)} s`, floor: 0 })
      : logScale(values, dollarTick)
  const axis = measure === 'accuracy' ? `Right answers (share of ${prompts} prompts)` : measure === 'time' ? 'Median time (seconds)' : 'Billed cost for all prompts (USD, log scale)'
  return (
    <ChartCard metric={measure === 'accuracy' ? 'accuracy' : measure === 'time' ? 'speed' : 'cost'} title="The fixed questions, told or not"
      subtitle={`${evaluation.title} · each row is one scenario, one setting and one scoring`}
      tools={<Segmented label="Measure" value={measure} onChange={setMeasure} options={[{ id: 'accuracy', label: 'Right answers' }, { id: 'time', label: 'Median time' }, { id: 'cost', label: 'Billed cost' }]} />}>
      <Dumbbell rows={dumbbells} scale={scale} series={['Router told about the change', 'Router with its old estimates']}
        label={`The fixed questions: ${axis}, told against old estimates, frozen and fixed scoring`} deltaLabel="Told vs old" axisLabel={axis} />
      <p className={explorers.chartNote}>Hover or focus a row for the results with nothing changed. The frozen and the fixed scoring face the same change, so compare the two rows of each scenario and setting.</p>
    </ChartCard>
  )
}

function DriftTable({ evaluation }: { evaluation: ScoringFixEvaluation }) {
  const find = (router: 'frozen' | 'fixed', scenario: string, strategy: string) =>
    evaluation[router].scenarios.find((item) => item.scenario.scenario_id === scenario)?.strategies.find((item) => item.strategy_id === strategy)
  const cell = (item: ScenarioStrategy | undefined) => (item ? <><span className={`${ui.num} ${ui.strong}`}>{item.correct}/{evaluation.prompts}</span><span className={`${ui.cellSub} ${ui.nowrap}`}>{usdOrFree(item.total_cost_usd)} · {seconds(item.median_latency_ms)}</span></> : '—')
  return (
    <div className={ui.tableWrap}>
      <table className={ui.table} aria-label="Mercury 3 retired next to Gemma 4 26B and Mercury 3 unavailable">
        <thead>
          <tr>
            <th rowSpan={2}>Setting</th><th rowSpan={2}>Scoring</th>
            <th colSpan={2}>{scenarioTitle(evaluation, MERCURY)}</th>
            <th colSpan={2}>{scenarioTitle(evaluation, GEMMA)}</th>
          </tr>
          <tr><th>Told</th><th>Old estimates</th><th>Told</th><th>Old estimates</th></tr>
        </thead>
        <tbody>
          {priorities.flatMap((priority) => (['frozen', 'fixed'] as const).map((router) => (
            <tr key={`${priority}:${router}`}>
              <td>{router === 'frozen' ? <strong>{priorityLabel[priority]}</strong> : ''}</td>
              <td>{routerName[router]}</td>
              <td>{cell(find(router, MERCURY, `learned:${priority}`))}</td>
              <td>{cell(find(router, MERCURY, `learned_frozen:${priority}`))}</td>
              <td>{cell(find(router, GEMMA, `learned:${priority}`))}</td>
              <td>{cell(find(router, GEMMA, `learned_frozen:${priority}`))}</td>
            </tr>
          )))}
        </tbody>
      </table>
    </div>
  )
}

export function ScoringFixSection({ report, evaluationId }: { report: ScoringFixReport; evaluationId: string }) {
  const evaluation = report.evaluations.find((item) => item.evaluation_id === evaluationId) ?? report.evaluations[report.evaluations.length - 1]
  const weight = (priority: RoutingPriority) => report.fixed_weights[priority].reliability
  const gemma = evaluation.fixed.scenarios.find((item) => item.scenario.scenario_id === GEMMA)?.scenario
  return (
    <Section id="scoring-fix" icon={<Wrench size={18} />} title="Fixing the scoring flaw"
      description="Robustness testing found two flaws in the frozen router's scoring: cost and time are divided by the largest value among the available models, so one model's price or speed change moves every other model's score, and reliability has no weight. The fix divides by fixed references from the frozen pool and gives reliability a small default weight, chosen on validation prompts only.">
      <Notice tone="info">
        This is a tested recommendation. The frozen router is still the evaluated system and nothing in it changed; the fresh prompts were read again and nothing was tuned on them.
        Reliability weight chosen on validation: {priorities.map((priority) => `${priorityLabel[priority].toLowerCase()} ${weight(priority)}`).join(', ')}.
      </Notice>
      <div className={ui.tableWrap} style={{ marginTop: '1rem' }}>
        <table className={ui.table} aria-label="The fixed questions and their answers">
          <thead><tr><th>Question, fixed before the results</th><th>Fresh</th><th>Test split</th><th>The numbers (fresh prompts)</th></tr></thead>
          <tbody>
            {report.questions.map((question) => (
              <tr key={question.question_id}>
                <td className={styles.scenario}><strong>{question.question}</strong><small>{question.rule}</small></td>
                <td><Badge tone={question.holds_fresh ? 'good' : 'bad'}>{question.holds_fresh ? 'Yes' : 'No'}</Badge></td>
                <td><Badge tone={question.holds_test ? 'good' : 'bad'}>{question.holds_test ? 'Yes' : 'No'}</Badge></td>
                <td className={styles.scenario}><small style={{ maxWidth: '34rem' }}>{question.answer_fresh}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: '1rem' }}>
        <FixChart evaluation={evaluation} rows={evidenceRows(report, evaluation.evaluation_id)} />
      </div>
      <h3 style={{ margin: '1.5rem 0 0.4rem', fontSize: '0.95rem' }}>Gemma 4 26B and Mercury 3 gone, next to Mercury 3 alone</h3>
      <p className={styles.small} style={{ marginBottom: '0.75rem' }}>{gemma?.description} Balanced matches fastest.</p>
      <DriftTable evaluation={evaluation} />
      <p className={styles.small} style={{ marginTop: '0.6rem' }}>{report.caveats.join(' ')}</p>
    </Section>
  )
}
