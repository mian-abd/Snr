import { ArrowRight, Calculator, Route as RouteIcon, ShieldCheck } from 'lucide-react'
import type { EvaluationSet } from '../api/types'
import { ShareBars } from '../charts/Charts'
import { ModelBars, type ModelBar } from '../charts/ModelBars'
import { ScatterLegend, TradeoffScatter, type TradeoffPoint } from '../charts/TradeoffScatter'
import { evaluationOf, find, priorityLabel, priorityOrder, studyRouterName, useFinalReport, useLearnedReport, useStudyReports, widest } from '../lib/data'
import { detailLines, fleetRows, listNames, routerName, routerRows, type FleetRow } from '../lib/fleet'
import { pct, seconds, usd } from '../lib/format'
import { Link } from '../lib/Link'
import { makersIn, modelColors } from '../lib/makers'
import { ButtonLink, ChartCard, Highlight, Highlights, Section, Skeleton } from '../ui'
import styles from './home.module.css'

const pctLabel = (value: number) => `${Math.round(value * 100)}%`
const costLabel = (value: number) => (value === 0 ? 'Free' : value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`)

function findings(evaluation: EvaluationSet, models: FleetRow[]) {
  const s = evaluation.strategies
  const byAccuracy = [...models].sort((a, b) => b.correct - a.correct || a.cost - b.cost)
  const leaders = byAccuracy.filter((m) => m.correct === byAccuracy[0]?.correct)
  const bySpeed = [...models].filter((m) => m.latencyMs != null).sort((a, b) => (a.latencyMs ?? 0) - (b.latencyMs ?? 0))
  const free = models.filter((m) => m.cost === 0)
  const paid = models.filter((m) => m.cost > 0).sort((a, b) => a.cost - b.cost)
  const bestFree = [...free].sort((a, b) => b.accuracy - a.accuracy)[0]
  const [lq, fs, lc, fc] = ['learned:quality', 'fixed_strongest', 'learned:cost', 'fixed_cheapest'].map((id) => find(s, id))
  return { byAccuracy, leaders, bySpeed, free, paid, bestFree, lq, fs, lc, fc }
}

export function HomePage() {
  const report = useFinalReport()
  const learned = useLearnedReport()
  const fresh = evaluationOf(report.data, 'final')
  const studies = useStudyReports()
  const study = widest(studies)
  const extended = study?.evaluations.find((item) => item.evaluation_id === 'final')
  const routerWord = studyRouterName[study?.study_id ?? 'flagship'] ?? 'Study router'
  const addedWord = study?.study_id === 'wide' ? 'the added models' : 'the flagships'
  const suitePrompts = learned.data?.matrix[0]?.prompts ?? 600

  if (!fresh) {
    return (
      <>
        <div className={styles.band}>
          <section className={styles.hero}>
            <div>
              <h1>Send every prompt to the model that’s good enough.</h1>
              <div className={styles.heroActions}>
                <ButtonLink to="/router" variant="primary" size="lg">Try the router<ArrowRight size={16} /></ButtonLink>
                <ButtonLink to="/research" size="lg">Read the research</ButtonLink>
              </div>
            </div>
            <div className={styles.heroText}>
              <p>An open study of routing language-model prompts by what they need: a small router predicts which model will answer correctly, then weighs that against price and speed.</p>
              <p>{report.isLoading ? 'Loading the results…' : 'The evaluation has not been run on this server yet, so there are no results to show.'}</p>
            </div>
          </section>
        </div>
        {report.isLoading && <div className={styles.loading}><Skeleton height={420} /></div>}
      </>
    )
  }

  // With a pool study, the charts show every measured model on the same fresh prompts.
  const matrix = extended?.matrix ?? fresh.matrix
  const models = fleetRows(matrix).filter((m) => m.served)
  const retired = fleetRows(matrix).filter((m) => !m.served)
  const flagshipIds = new Set(study?.added.map((model) => model.id) ?? [])
  const second = extended ? find(extended.strategies, 'learned:quality') : undefined
  const secondFast = extended ? find(extended.strategies, 'learned:latency') : undefined
  const frozenFast = extended ? find(extended.strategies, 'previous_router:latency') : undefined
  const fastGain = extended?.comparisons.find((item) => item.strategy_id === 'learned:latency' && item.baseline_id === 'previous_router:latency')
  const bestFlagship = models.filter((m) => flagshipIds.has(m.id)).sort((a, b) => b.correct - a.correct || a.cost - b.cost)[0]
  const f = findings(fresh, models)
  const routers = routerRows(fresh)
  const colors = modelColors(matrix.map((row) => row.model_id))

  const accuracyBars: ModelBar[] = [
    ...f.byAccuracy.map((m) => ({ id: m.id, name: m.name, value: m.accuracy, display: pctLabel(m.accuracy), modelId: m.id, local: m.local, details: detailLines(m.correct, m.prompts, m.cost, m.latencyMs) })),
    ...routers.map((r) => ({ id: r.strategy_id, name: routerName(r), value: r.accuracy, display: pctLabel(r.accuracy), kind: 'router' as const, details: detailLines(r.correct, r.prompts, r.total_cost_usd, r.median_latency_ms) })),
    ...(second ? [{ id: 'second:quality', name: `${routerWord} · Best quality`, value: second.accuracy, display: pctLabel(second.accuracy), kind: 'router' as const, details: detailLines(second.correct, second.prompts, second.total_cost_usd, second.median_latency_ms) }] : []),
    ...(secondFast ? [{ id: 'second:latency', name: `${routerWord} · Fastest`, value: secondFast.accuracy, display: pctLabel(secondFast.accuracy), kind: 'router' as const, details: detailLines(secondFast.correct, secondFast.prompts, secondFast.total_cost_usd, secondFast.median_latency_ms) }] : []),
  ].sort((a, b) => b.value - a.value)
  const costBars: ModelBar[] = [...f.paid, ...f.free].map((m) => ({ id: m.id, name: m.name, value: m.cost, display: costLabel(m.cost), modelId: m.id, local: m.local, details: detailLines(m.correct, m.prompts, m.cost, m.latencyMs) }))
    .sort((a, b) => b.value - a.value)
  const speedBars: ModelBar[] = f.bySpeed.map((m) => ({ id: m.id, name: m.name, value: (m.latencyMs ?? 0) / 1000, display: `${((m.latencyMs ?? 0) / 1000).toFixed(1)} s`, modelId: m.id, local: m.local, details: detailLines(m.correct, m.prompts, m.cost, m.latencyMs) }))
    .sort((a, b) => a.value - b.value)

  const scatter: TradeoffPoint[] = [
    ...models.map((m) => ({ id: m.id, label: m.name, kind: 'model' as const, modelId: m.id, x: m.cost, y: m.accuracy * 100, details: detailLines(m.correct, m.prompts, m.cost, m.latencyMs) })),
    ...routers.map((r) => ({ id: r.strategy_id, label: routerName(r), kind: 'router' as const, x: r.total_cost_usd, y: r.accuracy * 100, details: detailLines(r.correct, r.prompts, r.total_cost_usd, r.median_latency_ms) })),
    ...(second ? [{ id: 'second:quality', label: `${routerWord} · Best quality`, kind: 'router' as const, x: second.total_cost_usd, y: second.accuracy * 100, details: detailLines(second.correct, second.prompts, second.total_cost_usd, second.median_latency_ms) }] : []),
  ]
  const names = new Map(matrix.map((row) => [row.model_id, row.display_name.replace(/\s*\((free|local)\)/i, '')]))
  const shares = priorityOrder.map((priority) => {
    const strategy = find(fresh.strategies, `learned:${priority}`)
    const total = strategy ? Object.values(strategy.selected_models).reduce((sum, n) => sum + n, 0) : 0
    return {
      id: priority,
      label: priorityLabel[priority],
      meta: strategy ? `${strategy.correct}/${strategy.prompts} right · ${usd(strategy.total_cost_usd)}` : undefined,
      segments: strategy ? Object.entries(strategy.selected_models).map(([id, n]) => ({ id, name: names.get(id) ?? id, share: total ? n / total : 0 })) : [],
    }
  })
  const used = [...new Set(shares.flatMap((row) => row.segments.map((segment) => segment.id)))]
  const saved = f.lq && f.fs && f.fs.total_cost_usd > 0 ? 1 - f.lq.total_cost_usd / f.fs.total_cost_usd : null
  const savedCheap = f.lc && f.fc && f.fc.total_cost_usd > 0 ? 1 - f.lc.total_cost_usd / f.fc.total_cost_usd : null

  return (
    <>
      <div className={styles.band}>
        <section className={styles.hero}>
          <div>
            <h1>Send every prompt to the model that’s good enough.</h1>
            <div className={styles.heroActions}>
              <ButtonLink to="/router" variant="primary" size="lg">Try the router<ArrowRight size={16} /></ButtonLink>
              <ButtonLink to="/research" size="lg">Read the research</ButtonLink>
            </div>
          </div>
          <div className={styles.heroText}>
            <p>An open study of routing language-model prompts by what they need. We measured {matrix.length} models{flagshipIds.size ? `, ${flagshipIds.size} of them added later as ${study?.study_id === 'wide' ? 'flagship and budget models' : 'flagships'},` : ''} on {(suitePrompts + fresh.prompts).toLocaleString()} benchmark prompts in math, knowledge, and code, trained a small router on the results, and tested it on {fresh.prompts} fresh prompts it had never seen.</p>
            <p>Every number on this site comes from those runs, with what the providers actually billed, and can be downloaded. <Link to="/research?section=method" className={styles.inline}>Method and limits</Link></p>
          </div>
        </section>

        <Highlights columns={second && bestFlagship && secondFast ? 3 : 5}>
          <Highlight title="Accuracy" models={f.byAccuracy.slice(0, 4).map((m) => m.id)}>
            {f.leaders.length > 1
              ? <><b>{listNames(f.leaders.map((m) => m.name))}</b> tied for the most right answers ({f.leaders[0].correct} of {f.leaders[0].prompts}); {f.leaders[0].name} cost the least of them. Next: {listNames(f.byAccuracy.slice(f.leaders.length, f.leaders.length + 2).map((m) => m.name))}.</>
              : <><b>{listNames(f.byAccuracy.slice(0, 2).map((m) => `${m.name} (${pct(m.accuracy, 0)})`))}</b> answered the most fresh prompts right, followed by {listNames(f.byAccuracy.slice(2, 4).map((m) => m.name))}.</>}
          </Highlight>
          <Highlight title="Speed" models={f.bySpeed.slice(0, 4).map((m) => m.id)}>
            <b>{listNames(f.bySpeed.slice(0, 2).map((m) => `${m.name} (${seconds(m.latencyMs)})`))}</b> had the shortest median response, followed by {listNames(f.bySpeed.slice(2, 4).map((m) => m.name))}.
          </Highlight>
          <Highlight title="Price" models={[...f.free.map((m) => m.id).slice(0, 2), ...f.paid.slice(0, 2).map((m) => m.id)]}>
            {f.free.length} models cost nothing{f.bestFree ? <>; the best, <b>{f.bestFree.name}</b>, got {pct(f.bestFree.accuracy, 0)} right</> : ''}. The cheapest paid model, {f.paid[0]?.name}, cost {usd(f.paid[0]?.cost ?? 0)} for all {fresh.prompts}.
          </Highlight>
          {f.lq && f.fs && saved != null && (
            <Highlight title="Router · Best quality">
              <b>{Math.round(saved * 100)}% cheaper:</b> {f.lq.correct} of {f.lq.prompts} right for {usd(f.lq.total_cost_usd)}, against {f.fs.correct} for {usd(f.fs.total_cost_usd)} when every prompt goes to the strongest model.
            </Highlight>
          )}
          {second && bestFlagship && secondFast && frozenFast && (
            <Highlight title={study?.study_id === 'wide' ? 'More models' : 'Flagships'} models={[...flagshipIds].slice(0, 6)}>
              <b>{bestFlagship.name}</b> got {pct(bestFlagship.accuracy, 0)} right for {usd(bestFlagship.cost)} at {seconds(bestFlagship.latencyMs)}. With {addedWord} in the pool, the fastest setting got <b>{secondFast.correct} right instead of {frozenFast.correct}</b>{fastGain && fastGain.median_latency_difference_ci.high < 0 ? `, ${Math.abs(fastGain.median_latency_difference_ms / 1000).toFixed(1)} s quicker` : ''}; best quality got {second.correct}, against {f.lq?.correct ?? '—'} without them.
            </Highlight>
          )}
          {f.lc && f.fc && savedCheap != null && (
            <Highlight title="Router · Lowest cost">
              <b>{f.lc.correct} right for {usd(f.lc.total_cost_usd)}</b>, {Math.round(savedCheap * 100)}% less than always using the cheapest paid model ({f.fc.correct} right for {usd(f.fc.total_cost_usd)}).
            </Highlight>
          )}
        </Highlights>
      </div>

      <Section id="accuracy" title="Accuracy" description={`Each model answered the same ${fresh.prompts} fresh prompts: ${fresh.prompts_by_task.math ?? 0} math word problems, ${fresh.prompts_by_task.qa ?? 0} multiple-choice knowledge questions, and ${fresh.prompts_by_task.code ?? 0} Python functions checked by hidden tests. The hatched bars are the adaptive router, which picks one model per prompt.`}>
        <ChartCard metric="accuracy" title="Right answers on fresh prompts" subtitle={`Share of ${fresh.prompts} prompts answered correctly · higher is better`}
          footnotes={[
            { title: 'How answers are graded', body: 'Math answers must match the final number; multiple-choice answers must name the right letter; code passes only when every hidden EvalPlus test passes in a sandbox with no network. A call that fails counts as wrong.' },
            ...(retired.length ? [{ title: 'Models without answers', body: `${listNames(retired.map((m) => m.name))} ${retired.length === 1 ? 'was' : 'were'} retired by the provider before these prompts were sent, so ${retired.length === 1 ? 'it has' : 'they have'} no answers and ${retired.length === 1 ? 'is' : 'are'} left out of these charts. The live catalog check keeps the router from choosing ${retired.length === 1 ? 'it' : 'them'}.` }] : []),
          ]}>
          <ModelBars bars={accuracyBars} label="Right answers on fresh prompts" domain={[0, 1.08]} />
        </ChartCard>
      </Section>

      <div className={styles.pair}>
        <ChartCard metric="cost" title="Cost for all prompts" subtitle={`What the providers billed for ${fresh.prompts} prompts · lower is better`}>
          <ModelBars bars={costBars} label="Cost for all prompts" height={330} />
        </ChartCard>
        <ChartCard metric="speed" title="Response time" subtitle="Median seconds per prompt, end to end · lower is better">
          <ModelBars bars={speedBars} label="Median response time" height={330} />
        </ChartCard>
      </div>

      <Section id="tradeoff" title="Accuracy against cost" description="Up and to the left is better. The dotted line joins the cheapest model at each level of accuracy; a router point above it beats every single model at that price.">
        <ChartCard metric="route" title="Accuracy against cost" subtitle={`Right answers and billed cost for all ${fresh.prompts} prompts · cost on a log scale, free at the left`}
          tools={<ScatterLegend items={[
            ...makersIn(models.map((m) => m.id)).map((maker) => ({ name: maker.name, color: maker.color, shape: 'dot' as const })),
            { name: 'Adaptive router', shape: 'diamond' },
            { name: 'Cheapest at each accuracy', shape: 'line' },
          ]} />}>
          <TradeoffScatter points={scatter} xScale="symlog" frontier label="Accuracy against cost" xLabel="Cost for all prompts (USD, log scale)" yLabel="Right answers"
            formatX={(value) => (value === 0 ? 'Free' : value < 1 ? `$${Number(value.toPrecision(1))}` : `$${value}`)} />
        </ChartCard>
      </Section>

      <Section id="routing" title="Where the router sends prompts" description="The same router, four priorities. Each bar splits the fresh prompts by the model the router chose; the colors follow the model makers.">
        <ChartCard metric="route" title="Prompts per model, by priority" subtitle={`Share of ${fresh.prompts} fresh prompts sent to each model`}
          tools={<div className={styles.keyList}>{used.map((id) => <span key={id}><i style={{ background: colors.get(id) }} />{names.get(id) ?? id}</span>)}</div>}>
          <ShareBars rows={shares} colors={colors} label="Prompts per model, by priority" />
        </ChartCard>
      </Section>

      <Section id="how" title="How the router works">
        <div className={styles.steps}>
          <div className={styles.step}>
            <span className={styles.stepIcon}><Calculator size={18} /></span>
            <h3>Predict</h3>
            <p>A small logistic-regression model reads simple features of the prompt (task, length, numbers, code) and each model’s track record, and estimates the chance that each model answers correctly.</p>
          </div>
          <div className={styles.step}>
            <span className={styles.stepIcon}><RouteIcon size={18} /></span>
            <h3>Weigh</h3>
            <p>Each model gets a score: its chance of being right, minus penalties for expected cost, response time, and failures. Your priority sets the weights, from best quality to lowest cost.</p>
          </div>
          <div className={styles.step}>
            <span className={styles.stepIcon}><ShieldCheck size={18} /></span>
            <h3>Route</h3>
            <p>Hard requirements come first: a model its provider stopped serving, whose context is too small, or whose key is missing is never chosen. Then exactly one call goes to the winner.</p>
          </div>
        </div>
        <div className={styles.cta}>
          <div>
            <h3>Try it on your own prompt</h3>
            <p>See every model’s score before anything is sent. Nothing leaves this computer until you press Run.</p>
          </div>
          <ButtonLink to="/router" variant="primary" size="lg">Open the router<ArrowRight size={16} /></ButtonLink>
        </div>
      </Section>
    </>
  )
}
