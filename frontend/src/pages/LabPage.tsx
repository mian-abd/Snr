import { useQuery } from '@tanstack/react-query'
import { FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { client } from '../api/client'
import { BenchmarkPanel } from '../features/BenchmarkPanel'
import { ComparePanel } from '../features/ComparePanel'
import { EligibilityPanel } from '../features/EligibilityPanel'
import { RouterPanel } from '../features/RouterPanel'
import { useHealth } from '../lib/data'
import { PageHeader, Segmented, Skeleton } from '../ui'
import styles from './pages.module.css'

type Tool = 'rules' | 'compare' | 'benchmark' | 'context'

const tools: Array<{ id: Tool; label: string }> = [
  { id: 'rules', label: 'Rule-based router' },
  { id: 'compare', label: 'Compare models' },
  { id: 'benchmark', label: 'GSM8K pilot' },
  { id: 'context', label: 'Context filter' },
]

export function LabPage() {
  const [tool, setTool] = useState<Tool>('rules')
  const health = useHealth()
  const free = useQuery({ queryKey: ['models', 'baseline'], queryFn: () => client.models('baseline') })
  const paid = useQuery({ queryKey: ['models', 'paid'], queryFn: () => client.models('paid') })
  const ready = health.data && free.data && paid.data
  const pools = ready ? { baseline: free.data.models, paid: paid.data.models } : null
  const keyed = health.data?.credential_configured ?? false

  return (
    <>
      <PageHeader
        eyebrow={<><FlaskConical size={15} />Lab</>}
        title="Earlier tools, kept for transparency"
        description="The study started small: a hand-written rule router, side-by-side comparisons, and a twelve-question GSM8K pilot on two small model sets. They are kept here exactly as built, because the adaptive router is measured against them."
        actions={<Segmented label="Tool" value={tool} onChange={setTool} options={tools} />}
      />
      {!ready || !pools ? <Skeleton height={420} /> : (
        <div className={styles.labPanels}>
          {tool === 'rules' && <RouterPanel models={free.data!.models} credentialConfigured={keyed} />}
          {tool === 'compare' && <ComparePanel pools={pools} credentialConfigured={keyed} />}
          {tool === 'benchmark' && <BenchmarkPanel pools={pools} credentialConfigured={keyed} />}
          {tool === 'context' && <EligibilityPanel pools={pools} />}
        </div>
      )}
    </>
  )
}
