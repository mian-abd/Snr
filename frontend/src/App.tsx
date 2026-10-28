import * as Tabs from '@radix-ui/react-tabs'
import { useQuery } from '@tanstack/react-query'
import { client } from './api/client'
import { StatusBadge } from './components/StatusBadge'
import { BenchmarkPanel } from './features/BenchmarkPanel'
import { ComparePanel } from './features/ComparePanel'
import { EligibilityPanel } from './features/EligibilityPanel'
import { LearnedPanel } from './features/LearnedPanel'
import { RouterPanel } from './features/RouterPanel'
import styles from './App.module.css'

export default function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: client.health, refetchInterval: 10_000 })
  const models = useQuery({ queryKey: ['models', 'baseline'], queryFn: () => client.models('baseline') })
  const paidModels = useQuery({ queryKey: ['models', 'paid'], queryFn: () => client.models('paid') })

  if (health.isError || models.isError || paidModels.isError) {
    return <main className={styles.main}><p className={styles.error}>The backend could not be loaded. Confirm FastAPI is running on port 8000.</p></main>
  }
  if (!health.data || !models.data || !paidModels.data) return <main className={styles.main}><p className={styles.loading}>Loading checkpoint registry…</p></main>
  const pools = { baseline: models.data.models, paid: paidModels.data.models }

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.brand}><span className={styles.mark}>AR</span><div><strong>Adaptive LLM Router</strong><span>CP3 IN PROGRESS</span></div></div>
          <div className={styles.statusRail}>
            <StatusBadge status={health.data.status} label="Backend online" />
            <StatusBadge status={health.data.credential_configured ? 'success' : 'neutral'} label={health.data.credential_configured ? 'OpenRouter ready' : 'Key not configured'} />
            <StatusBadge status="neutral" label={models.data.snapshot_id} />
            <StatusBadge status="neutral" label={paidModels.data.snapshot_id} />
          </div>
        </div>
      </header>
      <main className={styles.main}>
        <section className={styles.intro}>
          <h1>Evidence first.<br /><span>Route with intent.</span></h1>
          <div className={styles.introAside}>A transparent rule policy selects from eligible, pinned models using a priority you can inspect and change.</div>
        </section>
        <Tabs.Root defaultValue="route">
          <Tabs.List className={styles.tabsList} aria-label="Checkpoint sections">
            <Tabs.Trigger className={styles.tab} value="route">01 Route</Tabs.Trigger>
            <Tabs.Trigger className={styles.tab} value="compare">02 Compare</Tabs.Trigger>
            <Tabs.Trigger className={styles.tab} value="eligibility">03 Eligibility</Tabs.Trigger>
            <Tabs.Trigger className={styles.tab} value="benchmark">04 Benchmark</Tabs.Trigger>
            <Tabs.Trigger className={styles.tab} value="learned">05 Learned</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="route"><RouterPanel models={models.data.models} credentialConfigured={health.data.credential_configured} /></Tabs.Content>
          <Tabs.Content value="compare"><ComparePanel pools={pools} credentialConfigured={health.data.credential_configured} /></Tabs.Content>
          <Tabs.Content value="eligibility"><EligibilityPanel pools={pools} /></Tabs.Content>
          <Tabs.Content value="benchmark"><BenchmarkPanel pools={pools} credentialConfigured={health.data.credential_configured} /></Tabs.Content>
          <Tabs.Content value="learned"><LearnedPanel /></Tabs.Content>
        </Tabs.Root>
        <footer className={styles.footer}><span>EXPLICIT RULE POLICY · FIXED MODEL IDENTITIES</span><span>SCHEMA 1.0 · {models.data.metadata_as_of.slice(0, 10)}</span></footer>
      </main>
    </div>
  )
}
