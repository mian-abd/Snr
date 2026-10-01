import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Beaker, Play, RotateCcw } from 'lucide-react'
import { client } from '../api/client'
import type { BenchmarkView } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import styles from './Panels.module.css'

const activeStatuses = new Set(['pending', 'running'])

function formatMetric(value: number | null, suffix = '') {
  return value == null ? '—' : `${Math.round(value).toLocaleString()}${suffix}`
}

export function BenchmarkPanel({ credentialConfigured }: { credentialConfigured: boolean }) {
  const queryClient = useQueryClient()
  const latest = useQuery({ queryKey: ['benchmark', 'latest'], queryFn: client.latestBenchmark, refetchInterval: (query) => activeStatuses.has(query.state.data?.manifest.status ?? '') ? 1500 : false })
  const runId = latest.data?.manifest.run_id
  const records = useQuery({ queryKey: ['benchmark-records', runId], queryFn: () => client.records(runId!), enabled: Boolean(runId) && !activeStatuses.has(latest.data?.manifest.status ?? '') })
  const start = useMutation({
    mutationFn: (mode: 'pilot' | 'full') => client.startBenchmark(mode),
    onSuccess: (data) => {
      queryClient.setQueryData<BenchmarkView | null>(['benchmark', 'latest'], data)
      void queryClient.invalidateQueries({ queryKey: ['benchmark', 'latest'] })
    },
  })
  const manifest = latest.data?.manifest
  const running = start.isPending || activeStatuses.has(manifest?.status ?? '')

  const begin = (mode: 'pilot' | 'full') => {
    const calls = mode === 'pilot' ? 4 : 24
    if (window.confirm(`Start the fixed ${mode} run? This schedules ${calls} logical model calls before retries.`)) start.mutate(mode)
  }

  return (
    <section className={styles.panel} aria-labelledby="benchmark-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>03 / BENCHMARK</span>
          <h2 id="benchmark-heading">A small baseline, captured completely.</h2>
          <p>Twelve fixed GSM8K questions establish the first objective model-quality evidence.</p>
        </div>
        {manifest && <StatusBadge status={manifest.status} />}
      </div>
      <div className={styles.protocolStrip}>
        {['GSM8K · test', '12 questions', '2 models', '24 cells', 'temperature 0', 'max 512 tokens', 'exact match'].map((label) => <span key={label}>{label}</span>)}
      </div>

      {manifest ? (
        <div className={styles.progressBlock} aria-live="polite">
          <div className={styles.progressLabels}><span>{manifest.run_id}</span><strong>{manifest.completed_cells} / {manifest.total_cells}</strong></div>
          <div className={styles.progressTrack}><span style={{ width: `${(manifest.completed_cells / manifest.total_cells) * 100}%` }} /></div>
          {manifest.error_message && <p className={styles.errorBox}>{manifest.error_message}</p>}
        </div>
      ) : (
        <div className={styles.emptyState}><Beaker size={20} /><span>No saved benchmark yet. Start with the four-call pilot.</span></div>
      )}

      <div className={styles.actionRow}>
        <div className={styles.secondaryActions}>
          <button disabled={!credentialConfigured || running} onClick={() => begin('pilot')}><Play size={15} /> Run pilot</button>
          <button disabled={!credentialConfigured || running} onClick={() => begin('full')}><Play size={15} /> Run benchmark</button>
        </div>
        <button className={styles.iconButton} onClick={() => latest.refetch()} aria-label="Refresh benchmark"><RotateCcw size={16} /></button>
      </div>
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
                <span className={record.exact_match ? styles.correct : styles.incorrect}>{record.exact_match ? 'correct' : 'incorrect'}</span>
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
