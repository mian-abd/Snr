import { useMutation } from '@tanstack/react-query'
import { Clock3, Route, ScanSearch } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { LearnedRouteRequest, RoutingPriority, RoutingWeights, TaskGroup } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import styles from './Panels.module.css'

type Props = { presets: Partial<Record<RoutingPriority, RoutingWeights>> }

const priorities: Array<{ id: RoutingPriority; label: string; description: string }> = [
  { id: 'balanced', label: 'Balanced', description: 'Accuracy, cost, and speed together.' },
  { id: 'cost', label: 'Lower cost', description: 'Cheapest without falling below the cheapest paid model.' },
  { id: 'quality', label: 'Higher quality', description: 'Most correct answers on validation.' },
  { id: 'latency', label: 'Faster response', description: 'Fastest without falling below the cheapest paid model.' },
]
const tasks: Array<{ id: TaskGroup | 'auto'; label: string }> = [
  { id: 'auto', label: 'Infer from prompt' }, { id: 'math', label: 'Math' }, { id: 'qa', label: 'Question answering' }, { id: 'code', label: 'Code' },
]
const sliders: Array<{ key: 'cost' | 'latency' | 'reliability'; label: string }> = [
  { key: 'cost', label: 'Cost weight' }, { key: 'latency', label: 'Latency weight' }, { key: 'reliability', label: 'Reliability weight' },
]
const fallback: RoutingWeights = { quality: 1, cost: 0.2, latency: 0.2, reliability: 0.5 }
const percent = (value: number) => `${Math.round(value * 100)}%`
const usd = (value: number) => (value === 0 ? 'Free' : `$${value.toFixed(5)}`)
const seconds = (value: number) => `${(value / 1000).toFixed(1)} s`

export function LearnedRouterForm({ presets }: Props) {
  const [prompt, setPrompt] = useState('A train travels 180 km in 2.5 hours. What is its average speed in km/h?')
  const [priority, setPriority] = useState<RoutingPriority>('balanced')
  const [task, setTask] = useState<TaskGroup | 'auto'>('auto')
  const [custom, setCustom] = useState<RoutingWeights | null>(null)
  const [minContext, setMinContext] = useState(1)
  const [lastAction, setLastAction] = useState<'preview' | 'route'>('preview')
  const weights = custom ?? presets[priority] ?? fallback
  const request = (): LearnedRouteRequest => ({
    prompt: prompt.trim(), priority, weights: custom, task_group: task === 'auto' ? null : task, min_context_tokens: minContext,
  })
  const preview = useMutation({ mutationFn: () => client.previewLearnedRoute(request()), onSuccess: () => setLastAction('preview') })
  const route = useMutation({ mutationFn: () => client.learnedRoute(request()), onSuccess: () => setLastAction('route') })
  const decision = lastAction === 'route' ? route.data?.decision ?? preview.data : preview.data ?? route.data?.decision
  const ranked = decision ? [...decision.candidates].sort((a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity)) : []
  const selected = decision?.candidates.find((item) => item.model_id === decision.selected_model_id)

  return (
    <section className={styles.dashboard} aria-labelledby="learned-route-heading">
      <div className={styles.dashboardHeading}><div><span className={styles.eyebrow}>Integrated learned router · logistic regression + multi-objective scoring</span><h3 id="learned-route-heading">Route a prompt with the learned router.</h3></div></div>
      <label className={styles.fieldLabel} htmlFor="learned-prompt">Prompt</label>
      <textarea id="learned-prompt" className={styles.prompt} value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={4} maxLength={50_000} />

      <fieldset className={styles.priorityFieldset}>
        <legend>What matters most? Each preset was tuned on the validation split.</legend>
        <div className={styles.priorityGrid}>
          {priorities.map((item) => (
            <button key={item.id} type="button" className={priority === item.id && !custom ? styles.priorityActive : styles.priorityOption} onClick={() => { setPriority(item.id); setCustom(null) }}>
              <strong>{item.label}</strong><span>{item.description}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className={styles.priorityFieldset}>
        <legend>Weights {custom ? '(custom)' : `(tuned ${priority} preset)`} · quality weight fixed at 1</legend>
        <div className={styles.weightGrid}>
          {sliders.map((slider) => (
            <label key={slider.key}>
              <span>{slider.label}<strong>{weights[slider.key].toFixed(2)}</strong></span>
              <input type="range" min={0} max={1} step={0.05} value={weights[slider.key]} onChange={(event) => setCustom({ ...weights, [slider.key]: Number(event.target.value) })} />
            </label>
          ))}
        </div>
        {custom && <div className={styles.secondaryActions}><button type="button" onClick={() => setCustom(null)}>Back to the tuned preset</button></div>}
      </fieldset>

      <div className={styles.requirementControl}>
        <div>
          <span className={styles.fieldLabel}>Task type and hard requirement</span>
          <p>The task type picks the model history used for prediction. Models below the minimum context, or without a configured key, are excluded first.</p>
        </div>
        <label htmlFor="learned-task">
          <span>Task type</span>
          <select id="learned-task" className={styles.inlineSelect} value={task} onChange={(event) => setTask(event.target.value as TaskGroup | 'auto')}>
            {tasks.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <label htmlFor="learned-min-context">
          <span>Minimum context</span>
          <input id="learned-min-context" type="number" min="1" step="1" value={minContext} onChange={(event) => setMinContext(Math.max(1, Number(event.target.value) || 1))} />
        </label>
      </div>

      <div className={styles.actionRow}>
        <p className={styles.disclaimer}>Preview never calls a provider. Routing sends one call (one retry on a timeout or rate limit) to the selected model, which may be a free external service.</p>
        <div className={styles.routeActions}>
          <button className={styles.secondaryRouteButton} disabled={!prompt.trim() || preview.isPending} onClick={() => preview.mutate()}>
            {preview.isPending ? <Clock3 className={styles.spin} size={16} /> : <ScanSearch size={16} />}{preview.isPending ? 'Scoring…' : 'Preview decision'}
          </button>
          <button className={styles.primaryButton} disabled={!prompt.trim() || route.isPending} onClick={() => route.mutate()}>
            {route.isPending ? <Clock3 className={styles.spin} size={16} /> : <Route size={16} />}{route.isPending ? 'Routing…' : 'Route prompt'}
          </button>
        </div>
      </div>
      {preview.error && <p className={styles.errorBox} role="alert">{preview.error.message}</p>}
      {route.error && <p className={styles.errorBox} role="alert">{route.error.message}</p>}

      {decision && (
        <div aria-live="polite">
          <div className={styles.routeOutcome}>
            <div className={styles.decisionBlock}>
              <span className={styles.eyebrow}>{lastAction === 'route' && route.data ? 'Selected model' : 'Previewed model'} · {decision.task_group}{decision.task_group_inferred ? ' (inferred)' : ''}</span>
              <h3>{selected?.display_name ?? decision.selected_model_id}</h3>
              <p>{decision.reason}</p>
              <div className={styles.signalRow}>{decision.task_signals.map((signal) => <span key={signal}>{signal}</span>)}</div>
              {selected && <p className={styles.eligibilityLine}>{selected.data_policy}</p>}
            </div>
            {lastAction === 'route' && route.data ? (
              <article className={styles.resultCard}>
                <header className={styles.resultHeader}><div><span className={styles.eyebrow}>Single routed result</span><h3>{route.data.result.requested_model_id}</h3></div><StatusBadge status={route.data.result.status} /></header>
                <div className={styles.responseText}>{route.data.result.text ?? route.data.result.error_message ?? 'The provider did not return usable text.'}</div>
                <dl className={styles.metricStrip}>
                  <div><dt>Latency</dt><dd>{Math.round(route.data.result.latency_ms).toLocaleString()} ms</dd></div>
                  <div><dt>Tokens</dt><dd>{route.data.result.total_tokens?.toLocaleString() ?? '—'}</dd></div>
                  <div><dt>Cost</dt><dd>{route.data.result.cost_usd == null ? 'Not reported' : `$${Number(route.data.result.cost_usd).toFixed(6)}`}</dd></div>
                </dl>
              </article>
            ) : <div className={styles.previewPanel}><span className={styles.eyebrow}>No provider call made</span><h3>Every model scored.</h3><p>Change the priority, the weights, or the requirement and preview again to see how the choice moves.</p></div>}
          </div>
          <div className={styles.tableWrap}>
            <table aria-label="Learned router candidate scores">
              <thead><tr><th>Model</th><th>P(success)</th><th>Expected cost</th><th>Expected latency</th><th>Failure rate</th><th>Score</th><th>Status</th></tr></thead>
              <tbody>{ranked.map((item) => (
                <tr key={item.model_id} className={item.model_id === decision.selected_model_id ? styles.selectedRow : undefined}>
                  <td><strong>{item.display_name}</strong><code>{item.model_id}</code></td>
                  <td className={styles.mono}>{percent(item.p_success)}</td>
                  <td className={styles.mono}>{usd(item.expected_cost_usd)}</td>
                  <td className={styles.mono}>{seconds(item.expected_latency_ms)}</td>
                  <td className={styles.mono}>{percent(item.failure_rate)}</td>
                  <td className={styles.mono} title={item.score == null ? undefined : `quality ${item.quality_term?.toFixed(3)} − cost ${item.cost_penalty?.toFixed(3)} − latency ${item.latency_penalty?.toFixed(3)} − reliability ${item.reliability_penalty?.toFixed(3)}`}>{item.score == null ? '—' : item.score.toFixed(3)}</td>
                  <td>{item.eligible ? <span className={styles.casePassed}>{item.model_id === decision.selected_model_id ? 'SELECTED' : 'ELIGIBLE'}</span> : <small className={styles.reason}>{item.exclusion_reason}</small>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className={styles.disclaimer}>Score = quality × P(success) − cost × normalized cost − latency × normalized latency − reliability × failure rate. Hover a score for its terms.</p>
        </div>
      )}
    </section>
  )
}
