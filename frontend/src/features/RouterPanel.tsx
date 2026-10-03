import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, Clock3, Route } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { ModelSpec, RoutingPriority } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import styles from './Panels.module.css'

type Props = { models: ModelSpec[]; credentialConfigured: boolean }

const priorities: Array<{ id: RoutingPriority; label: string; description: string }> = [
  { id: 'balanced', label: 'Balanced', description: 'Use simple prompt signals.' },
  { id: 'cost', label: 'Lower cost', description: 'Prefer the smaller baseline.' },
  { id: 'quality', label: 'Higher quality', description: 'Prefer the stronger baseline.' },
  { id: 'latency', label: 'Faster response', description: 'Prefer the smaller baseline.' },
]

export function RouterPanel({ models, credentialConfigured }: Props) {
  const [prompt, setPrompt] = useState('Explain why a router should separate hard requirements from user preferences.')
  const [priority, setPriority] = useState<RoutingPriority>('balanced')
  const route = useMutation({ mutationFn: () => client.route(prompt.trim(), priority) })
  const dashboard = useQuery({ queryKey: ['routing-dashboard'], queryFn: client.routingDashboard })
  const selectedModel = models.find((model) => model.id === route.data?.decision.selected_model_id)

  return (
    <section className={styles.panel} aria-labelledby="router-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>01 / ROUTE</span>
          <h2 id="router-heading">One explicit policy. One selected model.</h2>
          <p>Checkpoint 2 starts with understandable baselines and a rule-based decision. The policy never substitutes a hidden model.</p>
        </div>
        <div className={styles.modelPair} aria-label="Routing candidates">
          {models.map((model) => <span key={model.id}>{model.provider} · {model.context_length.toLocaleString()} ctx</span>)}
        </div>
      </div>

      <label className={styles.fieldLabel} htmlFor="route-prompt">Prompt</label>
      <textarea id="route-prompt" className={styles.prompt} value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={5} maxLength={50_000} />

      <fieldset className={styles.priorityFieldset}>
        <legend>What matters most?</legend>
        <div className={styles.priorityGrid}>
          {priorities.map((item) => (
            <button key={item.id} type="button" className={priority === item.id ? styles.priorityActive : styles.priorityOption} onClick={() => setPriority(item.id)}>
              <strong>{item.label}</strong><span>{item.description}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <div className={styles.actionRow}>
        <p className={styles.disclaimer}>Hard requirements still filter candidates before this priority policy runs.</p>
        <button className={styles.primaryButton} disabled={!credentialConfigured || !prompt.trim() || route.isPending} onClick={() => route.mutate()}>
          {route.isPending ? <Clock3 className={styles.spin} size={16} /> : <Route size={16} />}
          {route.isPending ? 'Selecting and routing…' : 'Route prompt'}
        </button>
      </div>

      {route.error && <p className={styles.errorBox} role="alert">{route.error.message}</p>}
      {route.data && (
        <div className={styles.routeOutcome} aria-live="polite">
          <div className={styles.decisionBlock}>
            <span className={styles.eyebrow}>Selected model</span>
            <h3>{selectedModel?.display_name ?? route.data.decision.selected_model_id}</h3>
            <p>{route.data.decision.reason}</p>
            <div className={styles.signalRow}>{route.data.decision.task_signals.map((signal) => <span key={signal}>{signal}</span>)}</div>
          </div>
          <article className={styles.resultCard}>
            <header className={styles.resultHeader}><div><span className={styles.eyebrow}>Single routed result</span><h3>{route.data.result.requested_model_id}</h3></div><StatusBadge status={route.data.result.status} /></header>
            <div className={styles.responseText}>{route.data.result.text ?? route.data.result.error_message ?? 'The provider did not return usable text.'}</div>
            <dl className={styles.metricStrip}>
              <div><dt>Latency</dt><dd>{Math.round(route.data.result.latency_ms).toLocaleString()} ms</dd></div>
              <div><dt>Tokens</dt><dd>{route.data.result.total_tokens?.toLocaleString() ?? '—'}</dd></div>
              <div><dt>Cost</dt><dd>{route.data.result.cost_usd == null ? 'Not reported' : `$${Number(route.data.result.cost_usd).toFixed(6)}`}</dd></div>
            </dl>
          </article>
        </div>
      )}

      <section className={styles.dashboard} aria-labelledby="strategy-dashboard-heading">
        <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>Offline strategy replay</span><h3 id="strategy-dashboard-heading">Same saved matrix, different decisions.</h3></div><ArrowRight size={18} aria-hidden="true" /></div>
        {dashboard.isError && <p className={styles.errorBox}>Saved routing replay could not be loaded.</p>}
        {dashboard.data && <>
          <p className={styles.disclaimer}>{dashboard.data.note} Source: {dashboard.data.source_dataset}, {dashboard.data.source_cells} cells.</p>
          <div className={styles.tableWrap}>
            <table><thead><tr><th>Strategy</th><th>Selected</th><th>Accuracy</th><th>Available</th><th>Mean latency</th><th>Cost</th></tr></thead>
              <tbody>{dashboard.data.strategies.map((strategy) => <tr key={strategy.strategy_id}>
                <td><strong>{strategy.label}</strong></td>
                <td className={styles.mono}>{Object.entries(strategy.selected_model_counts).map(([model, count]) => `${model.split('/')[0]} × ${count}`).join(', ')}</td>
                <td className={styles.metricStrong}>{(strategy.accuracy * 100).toFixed(1)}% <small>({strategy.correct}/{strategy.attempted})</small></td>
                <td>{strategy.successful}/{strategy.attempted}</td>
                <td className={styles.mono}>{strategy.mean_latency_ms == null ? '—' : `${Math.round(strategy.mean_latency_ms).toLocaleString()} ms`}</td>
                <td className={styles.mono}>{strategy.total_cost_usd == null ? '—' : `$${Number(strategy.total_cost_usd).toFixed(6)}`}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </>}
      </section>
    </section>
  )
}
