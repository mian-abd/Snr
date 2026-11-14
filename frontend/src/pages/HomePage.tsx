import { ArrowRight, BookOpen, Boxes, Calculator, HelpCircle, Route as RouteIcon, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import type { EvaluationSet, RoutingPriority } from '../api/types'
import { FlowDiagram } from '../charts/Charts'
import { evaluationOf, find, priorityLabel, priorityOrder, useFinalReport, useLearnedReport } from '../lib/data'
import { seconds, usd } from '../lib/format'
import { highlights } from '../lib/insights'
import { Link } from '../lib/Link'
import { ButtonLink, Segmented, Skeleton } from '../ui'
import styles from './pages.module.css'

function FlowCard({ evaluation }: { evaluation: EvaluationSet }) {
  const [priority, setPriority] = useState<RoutingPriority>('quality')
  const strategy = find(evaluation.strategies, `learned:${priority}`)
  const names = new Map(evaluation.matrix.map((row) => [row.model_id, row.display_name]))
  const total = strategy ? Object.values(strategy.selected_models).reduce((sum, value) => sum + value, 0) : 0
  const targets = strategy
    ? Object.entries(strategy.selected_models).map(([id, n]) => ({ id, name: names.get(id) ?? id, share: n / total }))
    : []
  return (
    <div className={styles.flowCard}>
      <div className={styles.between}>
        <div>
          <strong style={{ fontSize: '0.92rem' }}>Where {evaluation.prompts} fresh prompts went</strong>
          <p className={styles.small}>Each priority sends prompts to different models.</p>
        </div>
      </div>
      <div style={{ margin: '0.85rem 0 0.25rem' }}>
        <Segmented label="Priority" value={priority} onChange={setPriority} options={priorityOrder.map((id) => ({ id, label: priorityLabel[id] }))} />
      </div>
      <FlowDiagram targets={targets} label={`Models chosen under ${priorityLabel[priority]}`} />
      {strategy && (
        <div className={styles.flowFoot}>
          <span><strong>{strategy.correct}</strong> of {strategy.prompts} right</span>
          <span><strong>{usd(strategy.total_cost_usd)}</strong> total</span>
          <span>median <strong>{seconds(strategy.median_latency_ms)}</strong></span>
        </div>
      )}
    </div>
  )
}

export function HomePage() {
  const report = useFinalReport()
  const learned = useLearnedReport()
  const evaluation = evaluationOf(report.data, 'final') ?? evaluationOf(report.data, 'cp3_test')
  const items = evaluation ? highlights(evaluation) : []
  const suitePrompts = learned.data?.matrix[0]?.prompts ?? 600
  const freshPrompts = evaluationOf(report.data, 'final')?.prompts ?? 0
  const models = learned.data?.models.length ?? 9

  return (
    <>
      <section className={styles.hero}>
        <div>
          <div className={styles.row} style={{ marginBottom: '1.1rem' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', color: 'var(--accent)', fontSize: '0.84rem', fontWeight: 600 }}><Sparkles size={15} />Open research on cost-aware model routing</span>
          </div>
          <h1>Send every prompt to the model that's <span>good enough.</span></h1>
          <p className={styles.heroLead}>The adaptive router predicts which model will answer a prompt correctly, then weighs that against price and speed for what you care about. Every claim on this site is measured on public benchmarks, and every number can be downloaded.</p>
          <div className={styles.heroActions}>
            <ButtonLink to="/router" variant="primary" size="lg">Try the router<ArrowRight size={16} /></ButtonLink>
            <ButtonLink to="/research" size="lg">Read the research</ButtonLink>
          </div>
          <div className={styles.heroFacts}>
            <div><strong>{(suitePrompts + freshPrompts).toLocaleString()}</strong><span>benchmark prompts</span></div>
            <div><strong>{models}</strong><span>models, 3 providers</span></div>
            <div><strong>3</strong><span>tasks: math, knowledge, code</span></div>
          </div>
        </div>
        {evaluation ? <FlowCard evaluation={evaluation} /> : <Skeleton height={340} />}
      </section>

      {items.length > 0 && (
        <section aria-labelledby="findings" style={{ paddingTop: '1rem' }}>
          <div className={styles.between} style={{ marginBottom: '1rem' }}>
            <h2 id="findings" style={{ fontSize: '1.3rem' }}>What the experiments found</h2>
            <Link to="/research" style={{ color: 'var(--accent)', fontSize: '0.88rem', fontWeight: 550, textDecoration: 'none' }}>All results →</Link>
          </div>
          <div className={styles.grid4}>
            {items.map((item) => (
              <div key={item.label} className={styles.highlight}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <p>{item.text}</p>
              </div>
            ))}
          </div>
          <p className={styles.small} style={{ marginTop: '0.75rem' }}>Measured on {evaluation?.prompts} fresh benchmark prompts the router had never seen. Costs are what the providers billed.</p>
        </section>
      )}

      <section aria-labelledby="how" style={{ paddingTop: '3.5rem' }}>
        <h2 id="how" style={{ fontSize: '1.3rem', marginBottom: '1rem' }}>How it works</h2>
        <div className={styles.grid3}>
          <div className={styles.step}>
            <span className={styles.stepIcon}><Calculator size={18} /></span>
            <span className={styles.stepNo}>01 · Predict</span>
            <strong>Estimate each model's chance of being right</strong>
            <p>A small logistic-regression model reads simple features of the prompt (task, length, numbers, code) and each model's track record, and predicts the probability that the model answers correctly.</p>
          </div>
          <div className={styles.step}>
            <span className={styles.stepIcon}><RouteIcon size={18} /></span>
            <span className={styles.stepNo}>02 · Weigh</span>
            <strong>Trade it against cost and speed</strong>
            <p>Each model gets a score: chance of being right, minus penalties for expected cost, response time, and failures. Your priority sets the weights, from "best quality" to "lowest cost".</p>
          </div>
          <div className={styles.step}>
            <span className={styles.stepIcon}><ShieldCheck size={18} /></span>
            <span className={styles.stepNo}>03 · Route</span>
            <strong>Call one model, with guardrails</strong>
            <p>Hard requirements come first: a model whose provider stopped serving it, whose context is too small, or whose key is missing is never chosen. Then exactly one call goes to the winner.</p>
          </div>
        </div>
      </section>

      <section aria-labelledby="explore" style={{ paddingTop: '3.5rem' }}>
        <h2 id="explore" style={{ fontSize: '1.3rem', marginBottom: '1rem' }}>Explore</h2>
        <div className={styles.grid3}>
          <Link to="/models" className={styles.linkCard}><Boxes size={20} /><strong>Models</strong><span>Prices, context limits, live availability, and how accurate each model was on every task.</span><em>Browse models →</em></Link>
          <Link to="/research" className={styles.linkCard}><BookOpen size={20} /><strong>Research</strong><span>The full evaluation: leaderboard with confidence intervals, significance tests, errors, and robustness.</span><em>Read the results →</em></Link>
          <Link to="/faq" className={styles.linkCard}><HelpCircle size={20} /><strong>Questions</strong><span>Which model is best for math? How much does routing save? Is my prompt stored? Answered from the data.</span><em>Read the FAQ →</em></Link>
        </div>
      </section>
    </>
  )
}
