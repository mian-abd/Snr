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
  // The Checkpoint 3 pool's dated snapshot, from the learned-router report (absent until trained).
  const learned = useQuery({ queryKey: ['learned-report'], queryFn: client.learnedReport })

  if (health.isError || models.isError || paidModels.isError) {
    return <main className={styles.main}><p className={styles.error}>The backend could not be loaded. Confirm FastAPI is running on port 8000.</p></main>
  }
  if (!health.data || !models.data || !paidModels.data) return <main className={styles.main}><p className={styles.loading}>Loading checkpoint registry…</p></main>
  const pools = { baseline: models.data.models, paid: paidModels.data.models }

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.brand}><span className={styles.mark}>AR</span><div><strong>Adaptive LLM Router</strong><span>CHECKPOINT 3</span></div></div>
          <div className={styles.statusRail}>
            <StatusBadge status={health.data.status} label="Backend online" />
            <StatusBadge status={health.data.credential_configured ? 'success' : 'neutral'} label={health.data.credential_configured ? 'OpenRouter ready' : 'Key not configured'} />
            <StatusBadge status="neutral" label={models.data.snapshot_id} />
            <StatusBadge status="neutral" label={paidModels.data.snapshot_id} />
            {learned.data?.pool_snapshot_id && <StatusBadge status="neutral" label={`${learned.data.pool_snapshot_id}-cp3`} />}
          </div>
        </div>
      </header>
      <main className={styles.main}>
        <section className={styles.intro}>
          <h1>Evidence first.<br /><span>Route with intent.</span></h1>
          <div className={styles.introAside}>A learned router predicts each model's chance of answering correctly and weighs it against cost and speed for the priority you choose. The Checkpoint 2 rule router stays available for comparison.</div>
        </section>
        <Tabs.Root defaultValue="learned">
          <Tabs.List className={styles.tabsList} aria-label="Checkpoint sections">
            <Tabs.Trigger className={styles.tab} value="learned">01 Learned</Tabs.Trigger>
            <Tabs.Trigger className={styles.tab} value="route">02 Rule route</Tabs.Trigger>
            <Tabs.Trigger className={styles.tab} value="compare">03 Compare</Tabs.Trigger>
            <Tabs.Trigger className={styles.tab} value="eligibility">04 Eligibility</Tabs.Trigger>
            <Tabs.Trigger className={styles.tab} value="benchmark">05 Benchmark</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="learned"><LearnedPanel /></Tabs.Content>
          <Tabs.Content value="route"><RouterPanel models={models.data.models} credentialConfigured={health.data.credential_configured} /></Tabs.Content>
          <Tabs.Content value="compare"><ComparePanel pools={pools} credentialConfigured={health.data.credential_configured} /></Tabs.Content>
          <Tabs.Content value="eligibility"><EligibilityPanel pools={pools} /></Tabs.Content>
          <Tabs.Content value="benchmark"><BenchmarkPanel pools={pools} credentialConfigured={health.data.credential_configured} /></Tabs.Content>
        </Tabs.Root>
        <footer className={styles.footer}><span>LEARNED ROUTER · FIXED MODEL IDENTITIES</span><span>SCHEMA 1.0 · {models.data.metadata_as_of.slice(0, 10)}</span></footer>
      </main>
    </div>
  )
}
