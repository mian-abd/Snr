import type { EvaluationSet, FlagshipStudyReport, LearnedStrategyOutcome, RoutingPriority } from '../api/types'
import { IntervalRow } from '../charts/Charts'
import { ModelBars, type ModelBar } from '../charts/ModelBars'
import { costLine, timeLine, verdict } from '../lib/comparisons'
import { priorityLabel, priorityOrder } from '../lib/data'
import { detailLines, fleetRows } from '../lib/fleet'
import { pct, pValue, seconds, signed, span, usd } from '../lib/format'
import { Badge, Card, ChartCard, Highlight, Highlights, Meter, ModelLogo, Notice, Section } from '../ui'
import ui from '../ui/ui.module.css'
import styles from './pages.module.css'

const priorityOf = (id: string) => id.split(':')[1] as RoutingPriority

function share(strategy: LearnedStrategyOutcome | undefined, ids: Set<string>) {
  if (!strategy) return 0
  const total = Object.values(strategy.selected_models).reduce((sum, n) => sum + n, 0)
  const flagship = Object.entries(strategy.selected_models).filter(([id]) => ids.has(id)).reduce((sum, [, n]) => sum + n, 0)
  return total ? flagship / total : 0
}

function labeler(evaluation: EvaluationSet, report: FlagshipStudyReport) {
  const names = new Map(evaluation.matrix.map((row) => [row.model_id, row.display_name.replace(/\s*\((free|local)\)/i, '')]))
  const single = (id: string) => {
    const strategy = evaluation.strategies.find((item) => item.strategy_id === id)
    const model = strategy ? Object.keys(strategy.selected_models)[0] : undefined
    return model ? names.get(model) ?? model : id
  }
  return (id: string) => {
    if (id.startsWith('learned:')) return `With flagships · ${priorityLabel[priorityOf(id)]}`
    if (id.startsWith('previous_router:')) return `Without flagships · ${priorityLabel[priorityOf(id)]}`
    if (id.startsWith('oracle:')) return `Hindsight oracle · ${priorityLabel[priorityOf(id)]}`
    if (id.startsWith('model_task_prior:')) return `Per-task averages · ${priorityLabel[priorityOf(id)]}`
    if (id === 'fixed_top_flagship') return `Always ${names.get(report.strongest_flagship_id) ?? report.strongest_flagship_id}`
    if (id === 'fixed_strongest' || id === 'fixed_cheapest') return `Always ${single(id)}`
    if (id === 'rule_balanced') return 'Rule-based router'
    return id
  }
}

const groups: Array<{ title: string; ids: string[] }> = [
  { title: 'Router with the flagships', ids: priorityOrder.map((p) => `learned:${p}`) },
  { title: 'Router without them (frozen)', ids: priorityOrder.map((p) => `previous_router:${p}`) },
  { title: 'Single models', ids: ['fixed_top_flagship', 'fixed_strongest', 'fixed_cheapest'] },
  { title: 'Hindsight oracle over all models', ids: ['oracle:quality', 'oracle:cost'] },
]

export function FlagshipSection({ report, evaluationId }: { report: FlagshipStudyReport; evaluationId: string }) {
  const evaluation = report.evaluations.find((item) => item.evaluation_id === evaluationId) ?? report.evaluations[report.evaluations.length - 1]
  const flagshipIds = new Set(report.flagships.map((model) => model.id))
  const all = [...evaluation.strategies, ...evaluation.oracle]
  const get = (id: string) => all.find((item) => item.strategy_id === id)
  const label = labeler(evaluation, report)
  const spread = new Map(evaluation.uncertainty.map((item) => [item.strategy_id, item]))
  const models = fleetRows(evaluation.matrix).filter((row) => row.served)
  const flagships = models.filter((row) => flagshipIds.has(row.id)).sort((a, b) => b.correct - a.correct || a.cost - b.cost)
  const strongestPool = models.filter((row) => !flagshipIds.has(row.id)).sort((a, b) => b.correct - a.correct || a.cost - b.cost)[0]
  const [v2q, v1q, top, oracle] = ['learned:quality', 'previous_router:quality', 'fixed_top_flagship', 'oracle:quality'].map(get)
  const reach = Math.max(0.05, ...evaluation.comparisons.flatMap((item) => [item.accuracy_difference_ci.low, item.accuracy_difference_ci.high]).map(Math.abs)) * 1.1

  const bars: ModelBar[] = [
    ...models.map((row) => ({ id: row.id, name: row.name, value: row.accuracy, display: `${Math.round(row.accuracy * 100)}%`, modelId: row.id, local: row.local, details: detailLines(row.correct, row.prompts, row.cost, row.latencyMs) })),
    ...[v2q, v1q].filter((item): item is LearnedStrategyOutcome => Boolean(item)).map((item) => ({
      id: item.strategy_id, name: item.strategy_id.startsWith('learned') ? 'Router + flagships' : 'Router, frozen', value: item.accuracy, display: `${Math.round(item.accuracy * 100)}%`, kind: 'router' as const,
      details: detailLines(item.correct, item.prompts, item.total_cost_usd, item.median_latency_ms),
    })),
  ].sort((a, b) => b.value - a.value)

  return (
    <Section id="flagships" title="With flagship models" description={`${report.question} Four flagships (${report.flagships.map((model) => model.display_name).join(', ')}) answered the same prompts, and a second router was fit with exactly the same recipe on all ${evaluation.models.length} models. ${evaluation.title} · ${evaluation.prompts} prompts.`}>
      <div className={styles.stack}>
        <Highlights>
          {flagships[0] && strongestPool && (
            <Highlight title="Flagships alone" models={flagships.map((row) => row.id)}>
              <b>{flagships[0].name}</b> got {flagships[0].correct} of {flagships[0].prompts} right for {usd(flagships[0].cost)}; the strongest earlier model, {strongestPool.name}, got {strongestPool.correct} for {usd(strongestPool.cost)}.
            </Highlight>
          )}
          {v2q && v1q && (
            <Highlight title="Best quality, with flagships">
              <b>{v2q.correct} right for {usd(v2q.total_cost_usd)}</b>, against {v1q.correct} for {usd(v1q.total_cost_usd)} without them. {pct(share(v2q, flagshipIds), 0)} of prompts went to a flagship.
            </Highlight>
          )}
          {v2q && top && (
            <Highlight title="Against the strongest flagship" models={[report.strongest_flagship_id]}>
              Always using <b>{label('fixed_top_flagship').replace('Always ', '')}</b> got {top.correct} right for {usd(top.total_cost_usd)}; the router’s best-quality setting got {v2q.correct} for {usd(v2q.total_cost_usd)}.
            </Highlight>
          )}
          {oracle && (
            <Highlight title="Room left">
              Picking with hindsight among all {evaluation.models.length} models would get <b>{oracle.correct} of {oracle.prompts}</b> for {usd(oracle.total_cost_usd)}.
            </Highlight>
          )}
        </Highlights>

        {report.excluded_flagships.map((item) => (
          <Notice key={item.model_id} tone="warn"><strong>{item.display_name} is not in this comparison.</strong> {item.reason} Its {item.prompts_scored} answers cost {usd(item.spend_usd)} and are kept in the published data.</Notice>
        ))}

        <ChartCard metric="accuracy" title="Right answers, flagships included" subtitle={`Share of ${evaluation.prompts} prompts answered correctly · the hatched bars are the two routers`}>
          <ModelBars bars={bars} label="Right answers, flagships included" domain={[0, 1.08]} />
        </ChartCard>

        <div className={ui.tableWrap}>
          <table className={ui.table} aria-label="Flagship study strategies">
            <thead><tr><th>Strategy</th><th>Right answers</th><th>Paid cost</th><th>Median time</th><th>To flagships</th></tr></thead>
            <tbody>
              {groups.map((group) => {
                const members = group.ids.map(get).filter((item): item is LearnedStrategyOutcome => Boolean(item))
                if (!members.length) return null
                return [
                  <tr key={group.title} className={styles.groupRow}><td colSpan={5}>{group.title}</td></tr>,
                  ...members.map((item) => {
                    const interval = spread.get(item.strategy_id)
                    return (
                      <tr key={item.strategy_id}>
                        <td><span className={ui.cellTitle}>{label(item.strategy_id)}</span></td>
                        <td>
                          <div className={styles.accCell}>
                            <span className={`${ui.num} ${ui.strong}`}>{item.correct}/{item.prompts}</span>
                            <Meter value={item.accuracy} color={item.strategy_id.startsWith('learned') ? 'var(--ink)' : 'var(--text-3)'} label={pct(item.accuracy)} />
                          </div>
                          {interval && <span className={ui.cellSub}>{span(interval.accuracy, (x) => pct(x, 0))}</span>}
                        </td>
                        <td><span className={ui.num}>{usd(item.total_cost_usd)}</span></td>
                        <td><span className={ui.num}>{seconds(item.median_latency_ms)}</span></td>
                        <td><span className={ui.num}>{pct(share(item, flagshipIds), 0)}</span></td>
                      </tr>
                    )
                  }),
                ]
              })}
            </tbody>
          </table>
        </div>

        <Card pad={false}>
          <div className={styles.verdictGroup}>Questions fixed before the flagships’ results were read</div>
          {evaluation.comparisons.map((item) => {
            const result = verdict(item)
            return (
              <div key={`${item.strategy_id}-${item.baseline_id}`} className={styles.verdict}>
                <div>
                  <strong>{item.question}</strong>
                  <small>{label(item.strategy_id)} vs {label(item.baseline_id)} · {costLine(item)}{timeLine(item)}</small>
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

        <div className={ui.tableWrap}>
          <table className={ui.table} aria-label="Second router presets">
            <thead><tr><th>Second router</th><th>Cost weight</th><th>Speed weight</th><th>Reliability weight</th><th>Validation result</th></tr></thead>
            <tbody>
              {report.router.weight_tuning.map((item) => (
                <tr key={item.priority}>
                  <td><span className={ui.cellTitle}>{priorityLabel[item.priority]}</span></td>
                  <td className={ui.num}>{item.weights.cost}</td>
                  <td className={ui.num}>{item.weights.latency}</td>
                  <td className={ui.num}>{item.weights.reliability}</td>
                  <td className={ui.num}>{item.validation_correct}/{report.router.validation_prompts} · {usd(item.validation_cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={styles.small}>
          Fit on {report.router.training_rows.toLocaleString()} prompt-model pairs with {report.router.features} features ({report.router.family.replaceAll('_', ' ')}, chosen on validation log loss: {Object.entries(report.router.classifiers).map(([name, item]) => `${name.replaceAll('_', ' ')} ${item.validation.log_loss.toFixed(3)}`).join(', ')}; per-task averages {report.router.reference_model_task_prior.log_loss.toFixed(3)}).
          {' '}Flagship runs billed {usd(Object.values(report.spend_usd).reduce((sum, value) => sum + value, 0))} in all. {report.protocol[report.protocol.length - 1]}
          {' '}{flagships.length > 0 && <>Flagships: {flagships.map((row) => <span key={row.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginRight: 8 }}><ModelLogo id={row.id} size={13} />{row.name}</span>)}</>}
        </p>
      </div>
    </Section>
  )
}
