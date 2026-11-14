import { useMutation } from '@tanstack/react-query'
import { ArrowRight, Clock3, Coins, FlaskConical, Gauge, Globe2, HardDrive, Play, Scale, ScanSearch, Sparkles, Zap } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { LearnedCandidate, LearnedRouteRequest, RoutingPriority, RoutingWeights, TaskGroup, WhatIfChanges } from '../api/types'
import { accessLabel, priorityHint, priorityLabel, priorityOrder, providerLabel, useHealth, useLearnedReport } from '../lib/data'
import { pct, seconds, usdOrFree } from '../lib/format'
import { Badge, Button, Card, CardHeader, Empty, Meter, ModelAvatar, Notice, PageHeader, Stat } from '../ui'
import ui from '../ui/ui.module.css'
import styles from './pages.module.css'

const examples = [
  { label: 'Math word problem', text: 'A train travels 180 km in 2.5 hours. What is its average speed in km/h?' },
  { label: 'Multiple choice', text: 'Which gas makes up most of the Earth\'s atmosphere?\nA. Oxygen\nB. Nitrogen\nC. Carbon dioxide\nD. Argon' },
  { label: 'Python function', text: 'def second_largest(numbers: list[int]) -> int:\n    """Return the second largest distinct value in the list."""' },
  { label: 'Open question', text: 'Explain why the sky looks blue during the day but red at sunset.' },
]
const icons: Record<RoutingPriority, typeof Sparkles> = { quality: Sparkles, cost: Coins, latency: Zap, balanced: Scale }
const tasks: Array<{ id: TaskGroup | 'auto'; label: string }> = [
  { id: 'auto', label: 'Detect from the prompt' }, { id: 'math', label: 'Math' }, { id: 'qa', label: 'Knowledge (multiple choice)' }, { id: 'code', label: 'Code' },
]
const fallback: RoutingWeights = { quality: 1, cost: 0.2, latency: 0.2, reliability: 0 }
const destinations: Record<string, string> = {
  openrouter: 'OpenRouter, a third-party API, which passes it to the pinned host',
  ovhcloud: 'OVHcloud AI Endpoints, a third-party API used without an account',
  ollama: 'the Ollama server on this computer, so it never leaves the machine',
  google_ai_studio: 'Google AI Studio, a third-party API',
  nvidia_nim: 'NVIDIA NIM, a third-party API',
}
const taskNames: Record<string, string> = { math: 'Math', qa: 'Knowledge', code: 'Code' }
type Condition = 'latency' | 'price' | 'failure' | 'unavailable'
const conditions: Array<{ id: Condition; label: string; unit: string; initial: number }> = [
  { id: 'latency', label: 'Gets slower', unit: '× slower', initial: 3 },
  { id: 'price', label: 'Gets pricier', unit: '× the price', initial: 10 },
  { id: 'failure', label: 'Starts failing', unit: '% of calls', initial: 50 },
  { id: 'unavailable', label: 'Goes offline', unit: '', initial: 0 },
]

function changesFor(model: string, condition: Condition, value: number): WhatIfChanges {
  return {
    price_multipliers: condition === 'price' ? { [model]: value } : {},
    latency_multipliers: condition === 'latency' ? { [model]: value } : {},
    failure_shares: condition === 'failure' ? { [model]: Math.min(1, value / 100) } : {},
    unavailable: condition === 'unavailable' ? [model] : [],
  }
}

function CandidateRow({ item, selected }: { item: LearnedCandidate; selected: boolean }) {
  return (
    <div className={`${styles.candidate} ${selected ? styles.candidateSelected : ''} ${item.eligible ? '' : styles.candidateOut}`}>
      <div className={styles.candidateName}>
        <ModelAvatar model={{ id: item.model_id, display_name: item.display_name }} size={28} />
        <div>
          <strong>{item.display_name}</strong>
          <small title={item.exclusion_reason ?? item.catalog_note ?? undefined}>{item.eligible ? (item.catalog_note ?? accessLabel[item.access] ?? item.access) : item.exclusion_reason}</small>
        </div>
      </div>
      <div className={styles.pbar}><Meter value={item.p_success} label={`Chance right ${pct(item.p_success, 0)}`} /><span className={ui.num}>{pct(item.p_success, 0)}</span></div>
      <span className={ui.num} title={item.snapshot_expected_cost_usd != null ? `Was ${usdOrFree(item.snapshot_expected_cost_usd)} before the live price` : undefined}>{usdOrFree(item.expected_cost_usd)}</span>
      <span className={ui.num}>{seconds(item.expected_latency_ms)}</span>
      <span className={`${ui.num} ${selected ? ui.strong : ''}`} title={item.score == null ? undefined : `quality ${item.quality_term?.toFixed(3)} − cost ${item.cost_penalty?.toFixed(3)} − time ${item.latency_penalty?.toFixed(3)} − failures ${item.reliability_penalty?.toFixed(3)}`}>{item.score == null ? '—' : item.score.toFixed(2)}</span>
    </div>
  )
}

export function RouterPage() {
  const report = useLearnedReport()
  const health = useHealth()
  const presets: Partial<Record<RoutingPriority, RoutingWeights>> = Object.fromEntries(report.data?.weight_tuning.map((item) => [item.priority, item.weights]) ?? [])
  const [prompt, setPrompt] = useState(examples[0].text)
  const [priority, setPriority] = useState<RoutingPriority>('balanced')
  const [task, setTask] = useState<TaskGroup | 'auto'>('auto')
  const [custom, setCustom] = useState<RoutingWeights | null>(null)
  const [minContext, setMinContext] = useState(1)
  const [last, setLast] = useState<'preview' | 'route'>('preview')
  const weights = custom ?? presets[priority] ?? fallback
  const request = (): LearnedRouteRequest => ({ prompt: prompt.trim(), priority, weights: custom, task_group: task === 'auto' ? null : task, min_context_tokens: minContext })
  const preview = useMutation({ mutationFn: () => client.previewLearnedRoute(request()), onSuccess: () => setLast('preview') })
  const route = useMutation({ mutationFn: () => client.learnedRoute(request()), onSuccess: () => setLast('route') })
  const decision = last === 'route' ? route.data?.decision ?? preview.data : preview.data ?? route.data?.decision
  const ranked = decision ? [...decision.candidates].sort((a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity)) : []
  const chosen = decision?.candidates.find((item) => item.model_id === decision.selected_model_id)
  const [whatModel, setWhatModel] = useState<string | null>(null)
  const [condition, setCondition] = useState<Condition>('latency')
  const [factor, setFactor] = useState(3)
  const target = whatModel ?? decision?.selected_model_id ?? null
  const whatIf = useMutation({ mutationFn: (model: string) => client.learnedWhatIf(request(), changesFor(model, condition, factor)) })
  const names = new Map(decision?.candidates.map((item) => [item.model_id, item]))
  const local = chosen?.provider === 'ollama'
  const keyMissing = health.data && !health.data.credential_configured

  return (
    <>
      <PageHeader
        eyebrow={<><Sparkles size={15} />Router</>}
        title="Route a prompt"
        description="Choose what matters most. The router scores every model for this prompt and picks one. Previewing never sends your prompt anywhere."
      />
      <div className={styles.routerGrid}>
        <Card className={styles.sticky}>
          <label className={styles.label} htmlFor="prompt">Prompt</label>
          <textarea id="prompt" className={ui.textarea} rows={6} value={prompt} maxLength={50_000} onChange={(event) => setPrompt(event.target.value)} />
          <div className={styles.examples}>
            {examples.map((example) => <button key={example.label} type="button" className={styles.chip} onClick={() => setPrompt(example.text)}>{example.label}</button>)}
          </div>

          <span className={styles.label}>What matters most?</span>
          <div className={styles.priorities}>
            {priorityOrder.map((id) => {
              const Icon = icons[id]
              return (
                <button key={id} type="button" className={styles.priority} aria-pressed={priority === id && !custom} onClick={() => { setPriority(id); setCustom(null) }}>
                  <strong><Icon size={15} />{priorityLabel[id]}</strong>
                  <span>{priorityHint[id]}</span>
                </button>
              )
            })}
          </div>

          <details className={styles.advanced}>
            <summary>Advanced settings{custom ? ' · custom weights' : ''}<Gauge size={15} /></summary>
            <div className={styles.advancedBody}>
              <label className={ui.field}>Task type
                <select className={ui.select} value={task} onChange={(event) => setTask(event.target.value as TaskGroup | 'auto')}>
                  {tasks.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
              <label className={ui.field}>Minimum context window (tokens)
                <input className={ui.input} type="number" min={1} step={1} value={minContext} onChange={(event) => setMinContext(Math.max(1, Number(event.target.value) || 1))} />
              </label>
              <div className={styles.sliders}>
                {(['cost', 'latency', 'reliability'] as const).map((key) => (
                  <label key={key} className={styles.slider}>
                    <span>{{ cost: 'Cost weight', latency: 'Speed weight', reliability: 'Reliability weight' }[key]}<b>{weights[key].toFixed(2)}</b></span>
                    <input className={ui.range} type="range" min={0} max={1} step={0.05} value={weights[key]} onChange={(event) => setCustom({ ...weights, [key]: Number(event.target.value) })} />
                  </label>
                ))}
              </div>
              <p className={styles.small}>Accuracy always has weight 1. {custom ? <button type="button" className={styles.chip} onClick={() => setCustom(null)}>Back to the {priorityLabel[priority].toLowerCase()} preset</button> : `These are the tuned ${priorityLabel[priority].toLowerCase()} weights.`}</p>
            </div>
          </details>

          <div className={styles.actions}>
            <Button disabled={!prompt.trim() || preview.isPending} onClick={() => preview.mutate()}>
              {preview.isPending ? <Clock3 size={16} /> : <ScanSearch size={16} />}Preview decision
            </Button>
            <Button variant="primary" disabled={!prompt.trim() || route.isPending} onClick={() => route.mutate()}>
              {route.isPending ? <Clock3 size={16} /> : <Play size={16} />}{route.isPending ? 'Running…' : 'Run prompt'}
            </Button>
          </div>
          <p className={styles.small} style={{ marginTop: '0.75rem' }}>Run sends one call to the chosen model's provider (with one retry if it times out, is rate-limited, or hits a server error). Don't send personal or confidential text.{keyMissing && ' The OpenRouter key is not configured, so only free and local models can be chosen.'}</p>
        </Card>

        <div className={styles.stack}>
          {preview.error && <Notice tone="bad" role="alert">{preview.error.message}</Notice>}
          {route.error && <Notice tone="bad" role="alert">{route.error.message}</Notice>}
          {!decision && !preview.isPending && (
            <Empty icon={<ScanSearch size={22} />} title="No decision yet">Preview a decision to see which model the router picks and why. Nothing leaves this computer until you press Run.</Empty>
          )}
          {decision && chosen && (
            <Card>
              <div aria-live="polite">
                <div className={styles.decisionHead}>
                  <ModelAvatar model={{ id: chosen.model_id, display_name: chosen.display_name }} size={44} />
                  <div>
                    <small>{last === 'route' && route.data ? 'Sent to' : 'The router picks'}</small>
                    <h2>{chosen.display_name}</h2>
                  </div>
                </div>
                <div className={styles.row} style={{ marginTop: '0.75rem' }}>
                  <Badge tone="accent">{taskNames[decision.task_group]}{decision.task_group_inferred ? ' (detected)' : ''}</Badge>
                  <Badge>{priorityLabel[decision.priority]}{decision.custom_weights ? ', custom weights' : ''}</Badge>
                  <Badge>{accessLabel[chosen.access] ?? chosen.access}</Badge>
                  {decision.catalog_source === 'live' && <Badge tone="good" dot>Live catalog applied</Badge>}
                </div>
                <div className={styles.grid4} style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', marginTop: '1rem' }}>
                  <Stat label="Chance it's right" value={pct(chosen.p_success, 0)} />
                  <Stat label="Expected cost" value={usdOrFree(chosen.expected_cost_usd)} />
                  <Stat label="Expected time" value={seconds(chosen.expected_latency_ms)} />
                </div>
                <p className={styles.reason}>{decision.reason}</p>
                <div style={{ marginTop: '1rem' }}>
                  <Notice tone={local ? 'good' : 'warn'} icon={local ? <HardDrive size={16} /> : <Globe2 size={16} />}>
                    <strong>{last === 'route' && route.data ? 'Sent' : 'Run would send'} this prompt to {destinations[chosen.provider] ?? `${providerLabel[chosen.provider] ?? chosen.provider}, a third-party API`}.</strong> {chosen.data_policy}
                  </Notice>
                </div>
                {last === 'route' && route.data && (
                  <div style={{ marginTop: '1rem' }}>
                    <div className={styles.between}>
                      <strong style={{ fontSize: '0.9rem' }}>Response</strong>
                      <div className={styles.row}>
                        <Badge tone={route.data.result.status === 'success' ? 'good' : 'bad'} dot>{route.data.result.status.replaceAll('_', ' ')}</Badge>
                        <Badge>{Math.round(route.data.result.latency_ms).toLocaleString()} ms</Badge>
                        <Badge>{route.data.result.total_tokens?.toLocaleString() ?? '—'} tokens</Badge>
                        <Badge>{route.data.result.cost_usd == null ? 'cost not reported' : `$${Number(route.data.result.cost_usd).toFixed(6)}`}</Badge>
                      </div>
                    </div>
                    <div className={styles.response}>{route.data.result.text ?? route.data.result.error_message ?? 'The provider did not return usable text.'}</div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {decision && (
            <Card>
              <CardHeader title="How every model scored" description="Score = chance it's right − cost, time, and failure penalties under your weights. Models that fail a hard requirement are shown faded with the reason." />
              <div className={`${styles.candidate} ${styles.candidateHead}`}><span>Model</span><span>Chance right</span><span>Cost</span><span>Time</span><span>Score</span></div>
              {ranked.map((item) => <CandidateRow key={item.model_id} item={item} selected={item.model_id === decision.selected_model_id} />)}
            </Card>
          )}

          {decision && (
            <Card>
              <CardHeader title={<span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem' }}><FlaskConical size={16} />Stress-test this decision</span>} description="Change one condition for one model and see whether the choice moves. Nothing is sent to any provider." />
              <div className={styles.whatIfGrid}>
                <label className={ui.field}>Model
                  <select className={ui.select} value={target ?? ''} onChange={(event) => setWhatModel(event.target.value)}>
                    {decision.candidates.map((item) => <option key={item.model_id} value={item.model_id}>{item.display_name}</option>)}
                  </select>
                </label>
                <label className={ui.field}>What changes
                  <select className={ui.select} value={condition} onChange={(event) => {
                    const next = event.target.value as Condition
                    setCondition(next)
                    setFactor(conditions.find((item) => item.id === next)?.initial ?? 1)
                  }}>
                    {conditions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                  </select>
                </label>
                {condition !== 'unavailable'
                  ? <label className={ui.field}>{conditions.find((item) => item.id === condition)?.unit}
                      <input className={ui.input} type="number" min={condition === 'failure' ? 0 : 0.01} max={condition === 'failure' ? 100 : 1000} step="any" value={factor} onChange={(event) => setFactor(Number(event.target.value) || 0)} />
                    </label>
                  : <span />}
                <Button variant="primary" disabled={!target || whatIf.isPending || (condition !== 'unavailable' && factor <= 0)} onClick={() => target && whatIf.mutate(target)}>Simulate</Button>
              </div>
              {condition === 'failure' && weights.reliability === 0 && <p className={styles.small} style={{ marginTop: '0.6rem' }}>This preset gives reliability no weight, so failures will not change the score. Raise the reliability weight under Advanced settings to make them count.</p>}
              {whatIf.error && <div style={{ marginTop: '0.75rem' }}><Notice tone="bad" role="alert">{whatIf.error.message}</Notice></div>}
              {whatIf.data && (() => {
                const before = names.get(whatIf.data.before.selected_model_id)
                const after = whatIf.data.after.candidates.find((item) => item.model_id === whatIf.data.after.selected_model_id)
                return (
                  <div aria-live="polite">
                    <div className={styles.beforeAfter}>
                      <div>{before && <ModelAvatar model={{ id: before.model_id, display_name: before.display_name }} size={28} />}<div><small>Now</small><strong>{before?.display_name ?? whatIf.data.before.selected_model_id}</strong></div></div>
                      <ArrowRight size={18} color="var(--text-3)" />
                      <div className={whatIf.data.changed ? styles.changed : undefined}>{after && <ModelAvatar model={{ id: after.model_id, display_name: after.display_name }} size={28} />}<div><small>{whatIf.data.changed ? 'After the change' : 'After the change (unchanged)'}</small><strong>{after?.display_name ?? whatIf.data.after.selected_model_id}</strong></div></div>
                    </div>
                    <p className={styles.reason}>{whatIf.data.after.reason}</p>
                  </div>
                )
              })()}
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
