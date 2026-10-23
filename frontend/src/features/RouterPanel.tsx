import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2, Clock3, Route, ScanSearch, XCircle } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { ModelSpec, RoutingPool, RoutingPriority } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import styles from './Panels.module.css'

type Props = { models: ModelSpec[]; credentialConfigured: boolean }

const priorities: Array<{ id: RoutingPriority; label: string; description: Record<RoutingPool, string> }> = [
  { id: 'balanced', label: 'Balanced', description: { baseline: 'Escalate on visible effort signals.', paid: 'Tier by visible effort signals.' } },
  { id: 'cost', label: 'Lower cost', description: { baseline: 'Prefer the smaller baseline.', paid: 'Prefer the lowest-price model.' } },
  { id: 'quality', label: 'Higher quality', description: { baseline: 'Prefer the stronger baseline.', paid: 'Prefer the higher-capability model.' } },
  { id: 'latency', label: 'Faster response', description: { baseline: 'Prefer the smaller baseline.', paid: 'Prefer the low-latency model.' } },
]

const shortModel = (id: string) => (id.split('/')[1] ?? id).replace(':free', ' (free)')
const usd = (value: string | null) => (value == null ? '—' : `$${Number(value).toFixed(6)}`)
const ms = (value: number | null) => (value == null ? '—' : `${Math.round(value).toLocaleString()} ms`)

export function RouterPanel({ models, credentialConfigured }: Props) {
  const [prompt, setPrompt] = useState('Explain why a router should separate hard requirements from user preferences.')
  const [priority, setPriority] = useState<RoutingPriority>('balanced')
  const [pool, setPool] = useState<RoutingPool>('paid')
  const [minContextTokens, setMinContextTokens] = useState(1)
  const [lastAction, setLastAction] = useState<'preview' | 'route'>('preview')
  const preview = useMutation({
    mutationFn: () => client.previewRoute(prompt.trim(), priority, pool, minContextTokens),
    onSuccess: () => setLastAction('preview'),
  })
  const route = useMutation({
    mutationFn: () => client.route(prompt.trim(), priority, pool, minContextTokens),
    onSuccess: () => setLastAction('route'),
  })
  const [replayStrategy, setReplayStrategy] = useState('rule_balanced')
  const dashboard = useQuery({ queryKey: ['routing-dashboard', pool], queryFn: () => client.routingDashboard(pool) })
  const validation = useQuery({ queryKey: ['routing-validation', pool], queryFn: () => client.routingValidation(pool) })
  const paidModels = useQuery({ queryKey: ['routing-models'], queryFn: client.routingModels })
  const decision = lastAction === 'route'
    ? route.data?.decision ?? preview.data
    : preview.data ?? route.data?.decision
  const candidateModels = pool === 'paid' ? paidModels.data?.models ?? [] : models
  const selectedModel = candidateModels.find((model) => model.id === decision?.selected_model_id)
  const choosePool = (next: RoutingPool) => {
    setPool(next)
    preview.reset()
    route.reset()
  }
  const replayLabel = dashboard.data?.strategies.find((item) => item.strategy_id === replayStrategy)?.label

  return (
    <section className={styles.panel} aria-labelledby="router-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>01 / ROUTE</span>
          <h2 id="router-heading">One explicit policy. One selected model.</h2>
          <p>Choose the preserved two-model free pool from Checkpoint 1 or the dated three-model paid pool. The policy never substitutes a hidden model.</p>
        </div>
        <div className={styles.modelPair} aria-label="Routing candidates">
          {candidateModels.map((model) => <span key={model.id}>{shortModel(model.id)} · {model.context_length.toLocaleString()} ctx</span>)}
        </div>
      </div>

      <fieldset className={styles.priorityFieldset}>
        <legend>Model pool</legend>
        <div className={styles.poolGrid}>
          <button type="button" className={pool === 'paid' ? styles.priorityActive : styles.priorityOption} onClick={() => choosePool('paid')}>
            <strong>Checkpoint 2 paid pool</strong><span>Gemma, Mercury, and Gemini Argon with dated catalog pricing and 36-cell evidence.</span>
          </button>
          <button type="button" className={pool === 'baseline' ? styles.priorityActive : styles.priorityOption} onClick={() => choosePool('baseline')}>
            <strong>Checkpoint 1 free pool</strong><span>The original two fixed free identities and saved 24-cell evidence.</span>
          </button>
        </div>
      </fieldset>

      <label className={styles.fieldLabel} htmlFor="route-prompt">Prompt</label>
      <textarea id="route-prompt" className={styles.prompt} value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={5} maxLength={50_000} />

      <fieldset className={styles.priorityFieldset}>
        <legend>What matters most?</legend>
        <div className={styles.priorityGrid}>
          {priorities.map((item) => (
            <button key={item.id} type="button" className={priority === item.id ? styles.priorityActive : styles.priorityOption} onClick={() => setPriority(item.id)}>
              <strong>{item.label}</strong><span>{item.description[pool]}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <div className={styles.requirementControl}>
        <div>
          <span className={styles.fieldLabel}>Hard requirement</span>
          <p>Minimum context tokens. This filter runs before the selected priority.</p>
        </div>
        <label htmlFor="route-min-context">
          <span>Minimum context</span>
          <input id="route-min-context" type="number" min="1" step="1" value={minContextTokens} onChange={(event) => setMinContextTokens(Math.max(1, Number(event.target.value) || 1))} />
        </label>
        <button type="button" className={styles.requirementPreset} onClick={() => setMinContextTokens(500_000)}>Use 500,000 demo</button>
      </div>

      <div className={styles.actionRow}>
        <p className={styles.disclaimer}>Preview is local and never calls a provider. Routing sends one call only to the selected eligible model in the {pool === 'paid' ? 'paid' : 'free'} pool.</p>
        <div className={styles.routeActions}>
          <button className={styles.secondaryRouteButton} disabled={!prompt.trim() || preview.isPending} onClick={() => preview.mutate()}>
            {preview.isPending ? <Clock3 className={styles.spin} size={16} /> : <ScanSearch size={16} />}
            {preview.isPending ? 'Evaluating…' : 'Preview decision'}
          </button>
          <button className={styles.primaryButton} disabled={!credentialConfigured || !prompt.trim() || route.isPending} onClick={() => route.mutate()}>
            {route.isPending ? <Clock3 className={styles.spin} size={16} /> : <Route size={16} />}
            {route.isPending ? 'Selecting and routing…' : 'Route prompt'}
          </button>
        </div>
      </div>

      {preview.error && <p className={styles.errorBox} role="alert">{preview.error.message}</p>}
      {route.error && <p className={styles.errorBox} role="alert">{route.error.message}</p>}
      {decision && (
        <div className={styles.routeOutcome} aria-live="polite">
          <div className={styles.decisionBlock}>
            <span className={styles.eyebrow}>{route.data ? 'Selected model' : 'Previewed model'} · {decision.pool} pool</span>
            <h3>{selectedModel?.display_name ?? decision.selected_model_id}</h3>
            <p>{decision.reason}</p>
            <div className={styles.signalRow}>{decision.task_signals.map((signal) => <span key={signal}>{signal}</span>)}</div>
            <p className={styles.eligibilityLine}>{decision.eligible_model_ids.length} eligible model{decision.eligible_model_ids.length === 1 ? '' : 's'} after the {decision.min_context_tokens.toLocaleString()}-token requirement.</p>
          </div>
          {route.data ? <article className={styles.resultCard}>
              <header className={styles.resultHeader}><div><span className={styles.eyebrow}>Single routed result</span><h3>{route.data.result.requested_model_id}</h3></div><StatusBadge status={route.data.result.status} /></header>
              <div className={styles.responseText}>{route.data.result.text ?? route.data.result.error_message ?? 'The provider did not return usable text.'}</div>
              <dl className={styles.metricStrip}>
                <div><dt>Latency</dt><dd>{Math.round(route.data.result.latency_ms).toLocaleString()} ms</dd></div>
                <div><dt>Tokens</dt><dd>{route.data.result.total_tokens?.toLocaleString() ?? '—'}</dd></div>
                <div><dt>Cost</dt><dd>{route.data.result.cost_usd == null ? 'Not reported' : `$${Number(route.data.result.cost_usd).toFixed(6)}`}</dd></div>
              </dl>
            </article> : <div className={styles.previewPanel}><span className={styles.eyebrow}>No provider call made</span><h3>Decision preview complete.</h3><p>Change the priority or context requirement, then preview again to inspect the policy before routing.</p></div>}
        </div>
      )}

      <section className={styles.dashboard} aria-labelledby="policy-validation-heading">
        <div className={styles.dashboardHeading}>
          <div>
            <span className={styles.eyebrow}>Policy acceptance matrix · {validation.data?.strategy_id ?? (pool === 'paid' ? 'rule_based_paid_v1' : 'rule_based_v1')}</span>
            <h3 id="policy-validation-heading">Expected versus actual choices for fixed reference prompts.</h3>
          </div>
          {validation.data && (
            <span className={validation.data.passed ? styles.validationPassed : styles.validationFailed} aria-label={`${validation.data.passed_cases} of ${validation.data.total_cases} cases passed`}>
              {validation.data.passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
              {validation.data.passed_cases}/{validation.data.total_cases} passed
            </span>
          )}
        </div>
        <p className={styles.disclaimer}>These local checks cover each priority, the balanced effort signals, and the 500,000-token hard-requirement override. They make no provider calls.</p>
        {validation.isError && <p className={styles.errorBox}>The policy acceptance matrix could not be loaded.</p>}
        {validation.data && (
          <div className={styles.tableWrap}>
            <table>
              <thead><tr><th>Case</th><th>Priority</th><th>Minimum context</th><th>Expected</th><th>Actual</th><th>Result</th></tr></thead>
              <tbody>{validation.data.cases.map((item) => (
                <tr key={item.case_id}>
                  <td><strong>{item.label}</strong><code>{item.decision.reason}</code></td>
                  <td className={styles.mono}>{item.priority}</td>
                  <td className={styles.mono}>{item.min_context_tokens.toLocaleString()}</td>
                  <td className={styles.mono}>{shortModel(item.expected_model_id)}</td>
                  <td className={styles.mono}>{shortModel(item.decision.selected_model_id)}</td>
                  <td><span className={item.passed ? styles.casePassed : styles.caseFailed}>{item.passed ? 'PASS' : 'FAIL'}</span></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>

      <section className={styles.dashboard} aria-labelledby="strategy-dashboard-heading">
        <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>Results dashboard · offline strategy replay</span><h3 id="strategy-dashboard-heading">Same saved matrix, different decisions.</h3></div><ArrowRight size={18} aria-hidden="true" /></div>
        {dashboard.isError && <p className={styles.errorBox}>Saved routing replay could not be loaded for this pool.</p>}
        {dashboard.data && <>
          <p className={styles.disclaimer}>{dashboard.data.note} Source: {dashboard.data.source_dataset}, {dashboard.data.source_cells} cells ({dashboard.data.prompts.length} prompts × {dashboard.data.model_ids.length} models), run <code>{dashboard.data.source_run_id}</code>. Failed calls stay in the accuracy denominator; p95 uses the nearest-rank method.</p>
          <div className={styles.tableWrap}>
            <table><thead><tr><th>Strategy</th><th>Selected</th><th>Accuracy</th><th>Served</th><th>Median latency</th><th>p95 latency</th><th>Total cost</th><th>Cost / correct</th></tr></thead>
              <tbody>{dashboard.data.strategies.map((strategy) => <tr key={strategy.strategy_id} className={strategy.strategy_id === replayStrategy ? styles.selectedRow : undefined}>
                <td><strong>{strategy.label}</strong></td>
                <td className={styles.mono}>{Object.entries(strategy.selected_model_counts).map(([model, count]) => `${shortModel(model)} × ${count}`).join(', ')}</td>
                <td className={styles.metricStrong}>{(strategy.accuracy * 100).toFixed(1)}% <small>({strategy.correct}/{strategy.attempted})</small></td>
                <td>{strategy.successful}/{strategy.attempted}</td>
                <td className={styles.mono}>{ms(strategy.median_latency_ms)}</td>
                <td className={styles.mono}>{ms(strategy.p95_latency_ms)}</td>
                <td className={styles.mono}>{usd(strategy.total_cost_usd)}</td>
                <td className={styles.mono}>{usd(strategy.cost_per_correct_usd)}</td>
              </tr>)}</tbody>
            </table>
          </div>

          <div className={styles.replayControls}>
            <div>
              <span className={styles.eyebrow}>Per-prompt routing decisions</span>
              <h3>Which model each strategy selected, and why.</h3>
            </div>
            <label htmlFor="replay-strategy">
              <span>Strategy</span>
              <select id="replay-strategy" value={replayStrategy} onChange={(event) => setReplayStrategy(event.target.value)}>
                {dashboard.data.strategies.map((strategy) => <option key={strategy.strategy_id} value={strategy.strategy_id}>{strategy.label}</option>)}
              </select>
            </label>
          </div>
          <div className={styles.tableWrap}>
            <table aria-label={`Per-prompt decisions for ${replayLabel ?? replayStrategy}`}><thead><tr><th>Prompt</th><th>Signals</th><th>Selected model and reason</th><th>Outcome</th><th>Latency</th><th>Cost</th><th>All saved model outcomes</th></tr></thead>
              <tbody>{dashboard.data.prompts.map((item) => {
                const selection = item.selections.find((entry) => entry.strategy_id === replayStrategy)
                const cell = item.cells.find((entry) => entry.model_id === selection?.model_id)
                return <tr key={item.sample_id}>
                  <td className={styles.questionCell}><strong>GSM8K #{item.source_index}</strong><span title={item.question}>{item.question}</span></td>
                  <td><div className={styles.signalRow}>{item.task_signals.map((signal) => <span key={signal}>{signal}</span>)}</div></td>
                  <td><strong className={styles.mono}>{selection ? shortModel(selection.model_id) : '—'}</strong><code>{selection?.reason}</code></td>
                  <td>{cell == null ? '—' : cell.status !== 'success' ? <span className={styles.failure}>{cell.status.replaceAll('_', ' ')}</span> : <span className={cell.correct ? styles.casePassed : styles.caseFailed}>{cell.correct ? 'CORRECT' : 'WRONG'}</span>}</td>
                  <td className={styles.mono}>{cell ? ms(cell.latency_ms) : '—'}</td>
                  <td className={styles.mono}>{cell ? usd(cell.cost_usd) : '—'}</td>
                  <td><div className={styles.outcomeChips}>{item.cells.map((entry) => <span key={entry.model_id} className={entry.status !== 'success' ? styles.failure : entry.correct ? styles.casePassed : styles.caseFailed} title={entry.status}>{shortModel(entry.model_id)} {entry.status !== 'success' ? '!' : entry.correct ? '✓' : '✗'}</span>)}</div></td>
                </tr>
              })}</tbody>
            </table>
          </div>
        </>}
      </section>
    </section>
  )
}
