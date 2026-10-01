import * as Switch from '@radix-ui/react-switch'
import { useMutation } from '@tanstack/react-query'
import { Clock3, Database, Send, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import type { GenerationResult, ModelSpec } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import styles from './Panels.module.css'

type Props = { models: ModelSpec[]; credentialConfigured: boolean }

const samplePrompt =
  'Explain why alternating model order matters in a small latency benchmark. Keep the answer under 120 words.'

function failureGuidance(status: string) {
  if (status === 'rate_limited') {
    return {
      title: 'Shared free capacity is busy',
      action: 'Try again in a minute. For Gemma, adding your own Google provider key in OpenRouter Integrations gives requests account-level capacity.',
    }
  }
  if (status === 'provider_error') {
    return {
      title: 'Provider temporarily overloaded',
      action: 'This is upstream availability, not a problem with your app or OpenRouter key. Retry the comparison shortly.',
    }
  }
  if (status === 'timeout') {
    return { title: 'Provider timed out', action: 'Retry the same comparison; no configuration change is needed.' }
  }
  return { title: 'No usable result', action: 'Review the normalized request metadata, then try again.' }
}

function ResultCard({ result, model }: { result: GenerationResult; model?: ModelSpec }) {
  const success = result.status === 'success'
  const guidance = failureGuidance(result.status)
  return (
    <article className={styles.resultCard}>
      <header className={styles.resultHeader}>
        <div>
          <span className={styles.eyebrow}>{model?.provider ?? result.provider}</span>
          <h3>{model?.display_name ?? result.requested_model_id}</h3>
        </div>
        <StatusBadge status={result.status} />
      </header>
      {success ? (
        <div className={styles.responseText}>{result.text}</div>
      ) : (
        <div className={styles.errorBox} role="alert">
          <TriangleAlert size={16} />
          <div>
            <strong>{guidance.title}</strong>
            <p>{result.error_message ?? 'The provider did not return a usable response.'}</p>
            <p className={styles.errorGuidance}>{guidance.action}</p>
          </div>
        </div>
      )}
      <dl className={styles.metricStrip}>
        <div><dt>Latency</dt><dd>{Math.round(result.latency_ms).toLocaleString()} ms</dd></div>
        <div><dt>Tokens</dt><dd>{result.total_tokens?.toLocaleString() ?? '—'}</dd></div>
        <div><dt>Cost</dt><dd>{result.cost_usd == null ? 'Not reported' : `$${Number(result.cost_usd).toFixed(6)}`}</dd></div>
      </dl>
      <details className={styles.details}>
        <summary>Request metadata</summary>
        <dl className={styles.metadata}>
          <div><dt>Requested</dt><dd>{result.requested_model_id}</dd></div>
          <div><dt>Served</dt><dd>{result.served_model_id ?? 'Not reported'}</dd></div>
          <div><dt>Prompt tokens</dt><dd>{result.prompt_tokens ?? '—'}</dd></div>
          <div><dt>Completion tokens</dt><dd>{result.completion_tokens ?? '—'}</dd></div>
          <div><dt>Attempt</dt><dd>{result.attempt_number}</dd></div>
          <div><dt>Request ID</dt><dd>{result.request_id}</dd></div>
        </dl>
      </details>
    </article>
  )
}

export function ComparePanel({ models, credentialConfigured }: Props) {
  const [prompt, setPrompt] = useState(samplePrompt)
  const [save, setSave] = useState(false)
  const mutation = useMutation({ mutationFn: () => client.compare(prompt.trim(), save) })

  return (
    <section className={styles.panel} aria-labelledby="compare-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>01 / COMPARE</span>
          <h2 id="compare-heading">One prompt. Two fixed models.</h2>
          <p>Calls run concurrently for interaction speed. Benchmark timing uses a separate sequential protocol.</p>
        </div>
        <div className={styles.modelPair} aria-label="Pinned comparison models">
          {models.map((model) => <span key={model.id}>{model.provider} · {(model.context_length / 1000).toLocaleString()}k</span>)}
        </div>
      </div>

      <label className={styles.fieldLabel} htmlFor="comparison-prompt">Prompt</label>
      <textarea
        id="comparison-prompt"
        className={styles.prompt}
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        rows={6}
        maxLength={50_000}
      />
      <div className={styles.actionRow}>
        <label className={styles.switchLabel}>
          <Switch.Root className={styles.switchRoot} checked={save} onCheckedChange={setSave}>
            <Switch.Thumb className={styles.switchThumb} />
          </Switch.Root>
          <span><Database size={15} /> Save locally</span>
        </label>
        <button
          className={styles.primaryButton}
          disabled={!credentialConfigured || !prompt.trim() || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? <Clock3 className={styles.spin} size={16} /> : <Send size={16} />}
          {mutation.isPending ? 'Comparing…' : 'Compare models'}
        </button>
      </div>
      {!credentialConfigured && (
        <p className={styles.notice}>Add a replacement key to <code>backend/.env</code> to enable live calls.</p>
      )}
      {mutation.error && <p className={styles.errorBox} role="alert">{mutation.error.message}</p>}
      {mutation.data && (
        <div className={styles.resultsGrid} aria-live="polite">
          {mutation.data.results.map((result) => (
            <ResultCard key={result.request_id} result={result} model={models.find((model) => model.id === result.requested_model_id)} />
          ))}
        </div>
      )}
    </section>
  )
}
