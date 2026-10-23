import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Beaker, Play, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { BenchmarkEstimate, BenchmarkView, ModelSpec, RoutingPool } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import styles from './Panels.module.css'
import { PoolSwitch } from './PoolSwitch'

type Props = { pools: Record<RoutingPool, ModelSpec[]>; credentialConfigured: boolean }

const activeStatuses = new Set(['pending', 'running'])

function formatMetric(value: number | null, suffix = '') {
  return value == null ? '—' : `${Math.round(value).toLocaleString()}${suffix}`
}

export function BenchmarkPanel({ pools, credentialConfigured }: Props) {
  const queryClient = useQueryClient()
  const [pool, setPool] = useState<RoutingPool>('paid')
  const [pending, setPending] = useState<BenchmarkEstimate | null>(null)
  const latest = useQuery({ queryKey: ['benchmark', 'latest', pool], queryFn: () => client.latestBenchmark(pool), refetchInterval: (query) => activeStatuses.has(query.state.data?.manifest.status ?? '') ? 1500 : false })
  const runId = latest.data?.manifest.run_id
  const records = useQuery({ queryKey: ['benchmark-records', runId], queryFn: () => client.records(runId!), enabled: Boolean(runId) && !activeStatuses.has(latest.data?.manifest.status ?? '') })
  const estimate = useMutation({
    mutationFn: (mode: 'pilot' | 'full') => client.benchmarkEstimate(pool, mode),
    onSuccess: (data) => setPending(data),
  })
  const start = useMutation({
    mutationFn: ({ mode, confirmed }: { mode: 'pilot' | 'full'; confirmed?: string }) => client.startBenchmark(mode, pool, confirmed),
    onSuccess: (data) => {
      setPending(null)
      queryClient.setQueryData<BenchmarkView | null>(['benchmark', 'latest', pool], data)
      void queryClient.invalidateQueries({ queryKey: ['benchmark', 'latest', pool] })
    },
  })
  const manifest = latest.data?.manifest
  const running = start.isPending || activeStatuses.has(manifest?.status ?? '')
  const modelCount = pools[pool].length

  const choosePool = (next: RoutingPool) => {
    setPool(next)
    setPending(null)
    estimate.reset()
    start.reset()
  }

  const begin = (mode: 'pilot' | 'full') => {
    if (pool === 'paid') {
      // Paid runs show the worst-case estimate first and need an explicit confirmation.
      estimate.mutate(mode)
      return
    }
    const calls = (mode === 'pilot' ? 2 : 12) * modelCount
    if (window.confirm(`Start the fixed ${mode} run? This schedules ${calls} logical model calls before retries.`)) start.mutate({ mode })
  }

  return (
    <section className={styles.panel} aria-labelledby="benchmark-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>04 / BENCHMARK</span>
          <h2 id="benchmark-heading">A small baseline, captured completely.</h2>
          <p>The same twelve fixed GSM8K questions, prompt, and scorer run against each pool, so both matrices stay comparable.</p>
        </div>
        {manifest && <StatusBadge status={manifest.status} />}
      </div>
      <PoolSwitch
        value={pool}
        onChange={choosePool}
        descriptions={{
          paid: 'Gemma, Mercury, and Gemini Argon. Paid runs show a cost estimate and need confirmation.',
          baseline: 'The original free Gemma and Nemotron matrix from Checkpoint 1.',
        }}
      />
      <div className={styles.protocolStrip}>
        {['GSM8K · test', '12 questions', `${modelCount} models`, `${12 * modelCount} cells`, 'temperature 0', 'max 512 tokens', 'exact match'].map((label) => <span key={label}>{label}</span>)}
      </div>

      {manifest ? (
        <div className={styles.progressBlock} aria-live="polite">
          <div className={styles.progressLabels}><span>{manifest.run_id}</span><strong>{manifest.completed_cells} / {manifest.total_cells}</strong></div>
          <div className={styles.progressTrack}><span style={{ width: `${(manifest.completed_cells / manifest.total_cells) * 100}%` }} /></div>
          {manifest.error_message && <p className={styles.errorBox}>{manifest.error_message}</p>}
        </div>
      ) : (
        <div className={styles.emptyState}><Beaker size={20} /><span>No saved benchmark for this pool yet. Start with the {2 * modelCount}-call pilot.</span></div>
      )}

      <div className={styles.actionRow}>
        <div className={styles.secondaryActions}>
          <button disabled={!credentialConfigured || running || estimate.isPending} onClick={() => begin('pilot')}><Play size={15} /> Run pilot</button>
          <button disabled={!credentialConfigured || running || estimate.isPending} onClick={() => begin('full')}><Play size={15} /> Run benchmark</button>
        </div>
        <button className={styles.iconButton} onClick={() => latest.refetch()} aria-label="Refresh benchmark"><RotateCcw size={16} /></button>
      </div>
      {pending && (
        <div className={styles.estimateBox} role="dialog" aria-labelledby="estimate-heading">
          <span className={styles.eyebrow}>Confirm paid run</span>
          <h3 id="estimate-heading">Worst-case cost ${Number(pending.worst_case_usd).toFixed(4)} for {pending.cells} cells</h3>
          <p>{pending.mode} run · {pending.samples} questions × {pending.model_ids.length} models · cap ${pending.spend_cap_usd}. The estimate assumes every call uses the full 512-token budget and is retried once; actual spend is usually far lower.</p>
          {!pending.within_cap && <p className={styles.errorBox}>This estimate exceeds the spending cap, so the run cannot start.</p>}
          <div className={styles.estimateActions}>
            <button className={styles.primaryButton} disabled={!pending.within_cap || start.isPending} onClick={() => start.mutate({ mode: pending.mode, confirmed: pending.worst_case_usd })}><Play size={15} /> Confirm and start</button>
            <div className={styles.secondaryActions}><button onClick={() => setPending(null)}>Cancel</button></div>
          </div>
        </div>
      )}
      {estimate.error && <p className={styles.errorBox} role="alert">{estimate.error.message}</p>}
      {start.error && <p className={styles.errorBox} role="alert">{start.error.message}</p>}

      {latest.data?.summary && (
        <div className={styles.tableWrap}>
          <table>
            <thead><tr><th>Model</th><th>Accuracy</th><th>Correct</th><th>Median latency</th><th>Tokens</th><th>Cost</th><th>Failures</th></tr></thead>
            <tbody>{latest.data.summary.models.map((model) => (
              <tr key={model.model_id}>
                <td><code>{model.model_id}</code></td>
                <td className={styles.metricStrong}>{(model.accuracy * 100).toFixed(1)}%</td>
                <td>{model.correct} / {model.attempted}</td>
                <td>{formatMetric(model.median_latency_ms, ' ms')}</td>
                <td>{model.total_tokens.toLocaleString()}</td>
                <td>{model.total_cost_usd == null ? '—' : `$${Number(model.total_cost_usd).toFixed(6)}`}</td>
                <td>{model.failed}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {records.data && records.data.items.length > 0 && (
        <div className={styles.recordList}>
          <h3>Saved result records</h3>
          {records.data.items.map((record) => (
            <details key={`${record.sample_id}-${record.result.requested_model_id}`} className={styles.record}>
              <summary>
                <span>{record.sample_id} · {record.result.requested_model_id.split('/').at(-1)}</span>
                <span className={
                  record.result.status !== 'success'
                    ? styles.failure
                    : record.exact_match
                      ? styles.correct
                      : styles.incorrect
                }>
                  {record.result.status !== 'success'
                    ? record.result.status.replaceAll('_', ' ')
                    : record.exact_match
                      ? 'correct'
                      : 'incorrect'}
                </span>
              </summary>
              <div className={styles.recordBody}>
                <p>{record.rendered_prompt}</p>
                <dl className={styles.metadata}><div><dt>Expected</dt><dd>{record.expected_answer}</dd></div><div><dt>Extracted</dt><dd>{record.extracted_answer ?? 'Unparseable'}</dd></div><div><dt>Method</dt><dd>{record.extraction_method ?? 'None'}</dd></div></dl>
                <pre>{record.result.text ?? record.result.error_message}</pre>
              </div>
            </details>
          ))}
        </div>
      )}
      <p className={styles.disclaimer}>This 12-question sample verifies the experiment pipeline. It is not a statistically conclusive model ranking.</p>
    </section>
  )
}
