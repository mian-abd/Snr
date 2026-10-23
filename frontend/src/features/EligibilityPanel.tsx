import { useMutation } from '@tanstack/react-query'
import { Filter, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { client } from '../api/client'
import type { EligibilityResult, ModelSpec, RoutingPool } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import styles from './Panels.module.css'
import { poolLabels } from './pools'

type Props = { pools: Record<RoutingPool, ModelSpec[]> }

function perMillion(value: string | null) {
  if (value == null) return '—'
  const amount = Number(value) * 1_000_000
  if (amount === 0) return 'Free'
  return amount >= 1 ? `$${amount.toFixed(2)}` : `$${Number(amount.toPrecision(3))}`
}

export function EligibilityPanel({ pools }: Props) {
  const [minimum, setMinimum] = useState(500_000)
  const mutation = useMutation({ mutationFn: () => client.eligibility(minimum) })
  useEffect(() => { mutation.mutate() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const byModel = new Map<string, EligibilityResult>(mutation.data?.results.map((item) => [`${item.pool}:${item.model_id}`, item]))
  const rows = (['paid', 'baseline'] as const).flatMap((pool) => pools[pool].map((model) => ({ pool, model })))

  return (
    <section className={styles.panel} aria-labelledby="eligibility-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>03 / ELIGIBILITY</span>
          <h2 id="eligibility-heading">Hard requirements before routing.</h2>
          <p>A pure metadata filter checks every registered model in both pools before any generation call. Each pool comes from its own dated registry snapshot.</p>
        </div>
        <form className={styles.filterForm} onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}>
          <label htmlFor="minimum-context">Minimum context</label>
          <div>
            <input id="minimum-context" type="number" min={1} value={minimum} onChange={(event) => setMinimum(Number(event.target.value))} />
            <button type="submit"><Filter size={15} /> Evaluate</button>
          </div>
        </form>
      </div>
      <div className={styles.tableWrap}>
        <table>
          <thead><tr><th>Model</th><th>Pool</th><th>Context</th><th>Input</th><th>Capabilities</th><th>$ / 1M in · out</th><th>Decision</th></tr></thead>
          <tbody>
            {rows.map(({ pool, model }) => {
              const result = byModel.get(`${pool}:${model.id}`)
              return (
                <tr key={`${pool}:${model.id}`}>
                  <td><strong>{model.display_name}</strong><code>{model.id}</code></td>
                  <td className={styles.poolColumn}>{poolLabels[pool]}</td>
                  <td className={styles.mono}>{model.context_length.toLocaleString()}</td>
                  <td>{model.input_modalities.join(' · ')}</td>
                  <td>{[model.capabilities.tools && 'tools', model.capabilities.structured_output && 'structured'].filter(Boolean).join(' · ')}</td>
                  <td className={styles.mono}>{perMillion(model.pricing.prompt_per_token)} · {perMillion(model.pricing.completion_per_token)}</td>
                  <td>
                    {result ? <><StatusBadge status={result.eligible ? 'eligible' : 'excluded'} /><small className={styles.reason}>{result.reasons[0]}</small></> : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className={styles.proofLine}><ShieldCheck size={16} /> At 500,000 tokens, both Gemma entries (262,144) are excluded; Nemotron, Mercury 3, and Gemini 4 Argon remain eligible.</div>
    </section>
  )
}
