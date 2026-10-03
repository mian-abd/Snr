import { useMutation } from '@tanstack/react-query'
import { Filter, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { client } from '../api/client'
import type { EligibilityResult, ModelSpec } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import styles from './Panels.module.css'

export function EligibilityPanel({ models }: { models: ModelSpec[] }) {
  const [minimum, setMinimum] = useState(500_000)
  const mutation = useMutation({ mutationFn: () => client.eligibility(minimum) })
  useEffect(() => { mutation.mutate() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const byModel = new Map<string, EligibilityResult>(mutation.data?.results.map((item) => [item.model_id, item]))

  return (
    <section className={styles.panel} aria-labelledby="eligibility-heading">
      <div className={styles.sectionHeading}>
        <div>
          <span className={styles.index}>03 / ELIGIBILITY</span>
          <h2 id="eligibility-heading">Hard requirements before routing.</h2>
          <p>A pure metadata filter excludes models that cannot satisfy the request before any generation call.</p>
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
          <thead><tr><th>Model</th><th>Context</th><th>Input</th><th>Capabilities</th><th>Price / token</th><th>Decision</th></tr></thead>
          <tbody>
            {models.map((model) => {
              const result = byModel.get(model.id)
              return (
                <tr key={model.id}>
                  <td><strong>{model.display_name}</strong><code>{model.id}</code></td>
                  <td className={styles.mono}>{model.context_length.toLocaleString()}</td>
                  <td>{model.input_modalities.join(' · ')}</td>
                  <td>{[model.capabilities.tools && 'tools', model.capabilities.structured_output && 'structured'].filter(Boolean).join(' · ')}</td>
                  <td className={styles.mono}>{model.pricing.prompt_per_token === '0' ? 'Free' : model.pricing.prompt_per_token}</td>
                  <td>
                    {result ? <><StatusBadge status={result.eligible ? 'eligible' : 'excluded'} /><small className={styles.reason}>{result.reasons[0]}</small></> : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className={styles.proofLine}><ShieldCheck size={16} /> At 500,000 tokens, Gemma is excluded and Nemotron remains eligible.</div>
    </section>
  )
}
