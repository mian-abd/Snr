import { Check, ChevronLeft, ChevronRight, Minus, Search, SearchX, X } from 'lucide-react'
import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { ExplorerModel, ExplorerPrompt, PromptExplorer, RoutingPriority } from '../api/types'
import base from '../charts/charts.module.css'
import { accessLabel, addedLabel, evaluationLabel, priorityLabel, priorityOrder, strategyFamily, strategyLabel, usePrompts } from '../lib/data'
import { seconds, usd } from '../lib/format'
import { Link } from '../lib/Link'
import { makerOf } from '../lib/makers'
import { plainName, replaceRoute, taskLabel, taskOrder } from '../lib/measures'
import {
  benchmarkLabel, benchmarkOrder, excerpt, filterPrompts, listHref, matchesShow, optionLetter, pageSize, promptHref, readFilters, routerPick,
  searchText, shortStrategy, showHint, showLabel, shows, statusLabel, strategyRank, verdictLabel, verdictOf, type PromptFilters, type Show, type Verdict,
} from '../lib/prompts'
import { useRoute } from '../lib/router'
import { Badge, Button, ButtonLink, Empty, ModelLogo, PageHeader, Section, Segmented, Skeleton, Stat } from '../ui'
import ui from '../ui/ui.module.css'
import pages from './pages.module.css'
import styles from './prompts.module.css'

const verdictIcon = { right: Check, wrong: X, failed: Minus }
const verdictRank: Record<Verdict, number> = { right: 0, wrong: 1, failed: 2 }
const nameOf = (model: ExplorerModel | undefined, fallback: string) => (model ? plainName(model.display_name) : fallback)
const modelHref = (id: string) => `/models/${encodeURIComponent(id)}`

/** Right, wrong, or failed: always an icon and a word, never color alone. */
function VerdictMark({ verdict, detail }: { verdict: Verdict; detail?: string }) {
  const Icon = verdictIcon[verdict]
  return (
    <span className={styles.verdict} data-verdict={verdict}>
      <Icon size={13} strokeWidth={2.5} aria-hidden="true" />{verdictLabel[verdict]}{detail && <small>{detail}</small>}
    </span>
  )
}

/** Where the added models start, so the strip and its header leave a gap between the pools. */
const startsAddedGroup = (models: ExplorerModel[], index: number) => index > 0 && Boolean(models[index].added_from) && !models[index - 1].added_from

/** The models' logos, aligned with the cells of every strip below them. */
function StripHead({ models }: { models: ExplorerModel[] }) {
  return (
    <span className={styles.stripHead} aria-hidden="true">
      {models.map((model, index) => (
        <span key={model.model_id} className={styles.headCell} data-split={startsAddedGroup(models, index) ? '' : undefined} title={plainName(model.display_name)}>
          <ModelLogo id={model.model_id} size={14} local={model.access === 'local'} />
        </span>
      ))}
    </span>
  )
}

/**
 * One small mark per model: right, wrong, or a failed call, each with its own icon. Hovering a
 * mark names the model; from the keyboard the strip is one stop and the arrow keys move along it.
 * Screen readers hear the whole strip as one sentence.
 */
function OutcomeStrip({ prompt, models, pick, priority }: { prompt: ExplorerPrompt; models: ExplorerModel[]; pick: string | undefined; priority: RoutingPriority }) {
  const [active, setActive] = useState<number | null>(null)
  const [keyboard, setKeyboard] = useState(false)
  const pointer = useRef(false)
  const cells = models.map((model) => ({ model, outcome: prompt.outcomes[model.model_id], verdict: verdictOf(prompt.outcomes[model.model_id]) }))
  const right = cells.filter((cell) => cell.verdict === 'right').length
  const groups = (['right', 'wrong', 'failed'] as const)
    .map((verdict) => ({ verdict, names: cells.filter((cell) => cell.verdict === verdict).map((cell) => plainName(cell.model.display_name)) }))
    .filter((group) => group.names.length)
  const summary = `How each model did: ${right} of ${cells.length} right. ${groups.map((group) => `${verdictLabel[group.verdict]}: ${group.names.join(', ')}.`).join(' ')}`
  const current = active == null ? null : cells[active]
  const position = active ?? 0
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = { ArrowRight: position + 1, ArrowLeft: position - 1, Home: 0, End: cells.length - 1 }
    if (!(event.key in moves)) {
      if (event.key === 'Escape') setActive(null)
      return
    }
    event.preventDefault()
    setKeyboard(true)
    setActive((moves[event.key] + cells.length) % cells.length)
  }
  return (
    <div className={styles.strip} role="img" tabIndex={0} aria-label={summary}
      onPointerDown={() => { pointer.current = true }}
      onFocus={() => { setKeyboard(!pointer.current); pointer.current = false; setActive((index) => index ?? 0) }}
      onBlur={() => { setKeyboard(false); setActive(null) }}
      onPointerLeave={(event) => { if (!keyboard && event.pointerType === 'mouse') setActive(null) }}
      onKeyDown={onKeyDown}>
      {cells.map((cell, index) => {
        const Icon = verdictIcon[cell.verdict]
        return (
          <span key={cell.model.model_id} className={styles.cell} data-verdict={cell.verdict}
            data-pick={cell.model.model_id === pick ? '' : undefined} data-active={index === active ? '' : undefined}
            data-split={startsAddedGroup(models, index) ? '' : undefined} onPointerEnter={() => setActive(index)}>
            <Icon size={10} strokeWidth={3.25} aria-hidden="true" />
          </span>
        )
      })}
      {current && (
        <span className={`${base.tooltip} ${styles.stripTip}`} style={{ left: `clamp(5.5rem, ${((position + 0.5) / cells.length) * 100}%, calc(100% - 5.5rem))` }}>
          <strong>{plainName(current.model.display_name)}</strong>
          <span>{verdictLabel[current.verdict]}{current.outcome ? ` · ${seconds(current.outcome.latency_ms)} · ${usd(current.outcome.cost_usd)}` : ''}</span>
          {current.verdict === 'failed' && current.outcome && <span>{statusLabel[current.outcome.status] ?? current.outcome.status}</span>}
          {current.model.model_id === pick && <span>Router's pick · {priorityLabel[priority]}</span>}
          {keyboard && <span className={styles.tipHint}>Arrow keys for the other models</span>}
        </span>
      )}
    </div>
  )
}

function RouterPick({ prompt, models, priority }: { prompt: ExplorerPrompt; models: ExplorerModel[]; priority: RoutingPriority }) {
  const pick = routerPick(prompt, priority)
  if (!pick) return <span className={ui.muted}>—</span>
  const model = models.find((item) => item.model_id === pick)
  return (
    <div className={styles.pick}>
      <span className={styles.pickLabel}>Router · {priorityLabel[priority]}</span>
      <span className={styles.pickModel}>
        <ModelLogo id={pick} size={16} local={model?.access === 'local'} />
        <span className={styles.pickName}>{nameOf(model, pick)}</span>
      </span>
      <VerdictMark verdict={verdictOf(prompt.outcomes[pick])} />
    </div>
  )
}

function Legend() {
  return (
    <ul className={styles.legend} aria-label="Key">
      {(['right', 'wrong', 'failed'] as const).map((verdict) => {
        const Icon = verdictIcon[verdict]
        return <li key={verdict}><span className={styles.cell} data-verdict={verdict} aria-hidden="true"><Icon size={10} strokeWidth={3.25} /></span>{verdictLabel[verdict]}</li>
      })}
      <li><span className={styles.cell} data-pick="" aria-hidden="true" />Underlined: the router's pick</li>
    </ul>
  )
}

/** The models of the frozen pool, and a sentence on the ones added later or left out. */
function PoolNote({ data }: { data: PromptExplorer }) {
  const added = data.models.filter((model) => model.added_from)
  const frozen = data.models.length - added.length
  const list = (models: ExplorerModel[]) => models.map((model) => plainName(model.display_name)).join(', ')
  return (
    <p className={styles.note}>
      The router's picks come from the frozen adaptive router, which chooses among the {frozen} models it was trained with.
      {added.length > 0 && ` ${list(added)} ${added.length === 1 ? 'was' : 'were'} added later for the pool studies and ${added.length === 1 ? 'is' : 'are'} shown for comparison only.`}
      {data.excluded.length > 0 && ` ${list(data.excluded)} answered only some of these prompts, so ${data.excluded.length === 1 ? 'it is' : 'they are'} left out.`}
      {' '}A failed call counts as wrong. <Link to="/research?section=method" className={styles.more}>How answers were graded</Link>
    </p>
  )
}

/** Searchable text per prompt, built once per prompt set. */
function useSearchTexts(data: PromptExplorer | null | undefined) {
  return useMemo(() => new Map((data?.prompts ?? []).map((prompt) => [prompt.sample_id, searchText(prompt)])), [data])
}

export function PromptsPage() {
  const { query } = useRoute()
  const filters = readFilters(query)
  const explorer = usePrompts(filters.set)
  const data = explorer.data
  const texts = useSearchTexts(data)
  const listRef = useRef<HTMLDivElement>(null)
  const ids = useId()
  const update = (change: Partial<PromptFilters>) => replaceRoute(listHref({ ...filters, page: 1, ...change }))

  const header = (
    <PageHeader
      eyebrow="Research"
      title="Every prompt, every answer"
      description="Each prompt of the evaluation with how every model did on it and where the adaptive router sent it. Filter to the prompts the router got wrong, or the ones no model could answer, and open any prompt for its full text, the expected answer, and every model's time and cost."
    />
  )
  const setToggle = (
    <Segmented label="Prompt set" value={filters.set} onChange={(set) => update({ set })}
      options={(['final', 'cp3_test'] as const).map((id) => ({ id, label: evaluationLabel[id].title, title: evaluationLabel[id].about }))} />
  )
  if (explorer.isLoading) return <>{header}<Skeleton height={520} /></>
  if (!data) {
    return (
      <>
        {header}
        <div className={pages.controls}>{setToggle}</div>
        <div style={{ marginTop: '1.25rem' }}>
          {explorer.isError
            ? <Empty icon={<SearchX size={22} />} title="The prompts could not be loaded">{explorer.error instanceof Error ? explorer.error.message : 'Try reloading the page.'}</Empty>
            : <Empty icon={<SearchX size={22} />} title="No prompt data on this server">The prompt sets and the scored answers are read from the committed files under <code>data/</code>.</Empty>}
        </div>
      </>
    )
  }

  const models = data.models
  const tasks = taskOrder.filter((task) => data.prompts.some((prompt) => prompt.task_group === task))
  const taskOfBenchmark = new Map(data.prompts.map((prompt) => [prompt.benchmark, prompt.task_group]))
  const benchmarks = benchmarkOrder.filter((id) => taskOfBenchmark.has(id) && (filters.task === 'all' || taskOfBenchmark.get(id) === filters.task))
  const scope = filterPrompts(data.prompts, models, { ...filters, show: 'all' }, texts)
  const counts = Object.fromEntries(shows.map((show) => [show, scope.filter((prompt) => matchesShow(prompt, models, show, filters.priority)).length])) as Record<Show, number>
  const rows = scope.filter((prompt) => matchesShow(prompt, models, filters.show, filters.priority))
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const page = Math.min(filters.page, pageCount)
  const shown = rows.slice((page - 1) * pageSize, page * pageSize)
  const routerRight = rows.filter((prompt) => {
    const pick = routerPick(prompt, filters.priority)
    return pick != null && prompt.outcomes[pick]?.correct
  }).length
  const filtered = filters.task !== 'all' || filters.bench !== 'all' || filters.show !== 'all' || filters.q.trim() !== ''
  const goTo = (next: number) => {
    replaceRoute(listHref({ ...filters, page: next }))
    listRef.current?.scrollIntoView({ block: 'start' })
  }
  const current = { ...filters, page }

  return (
    <>
      {header}
      <div className={pages.controls}>
        {setToggle}
        <Segmented label="Router priority" value={filters.priority} onChange={(priority) => update({ priority })}
          options={priorityOrder.map((id) => ({ id, label: priorityLabel[id] }))} />
      </div>
      <p className={pages.small} style={{ marginTop: '0.6rem' }}>{evaluationLabel[data.evaluation].about}</p>

      <div className={styles.toolbar}>
        <div className={`${styles.field} ${styles.searchField}`}>
          <label htmlFor={`${ids}-search`}>Search</label>
          <span className={styles.searchBox}>
            <Search size={15} aria-hidden="true" />
            <input id={`${ids}-search`} className={ui.input} type="search" placeholder="Words in the prompt or its ID" value={filters.q} onChange={(event) => update({ q: event.target.value })} />
          </span>
        </div>
        <div className={styles.field}>
          <label htmlFor={`${ids}-task`}>Task</label>
          <select id={`${ids}-task`} className={ui.select} value={filters.task} onChange={(event) => {
            const task = event.target.value
            update({ task, bench: task === 'all' || taskOfBenchmark.get(filters.bench) === task ? filters.bench : 'all' })
          }}>
            <option value="all">All tasks</option>
            {tasks.map((task) => <option key={task} value={task}>{taskLabel[task]}</option>)}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor={`${ids}-bench`}>Benchmark</label>
          <select id={`${ids}-bench`} className={ui.select} value={filters.bench} onChange={(event) => update({ bench: event.target.value })}>
            <option value="all">All benchmarks</option>
            {benchmarks.map((id) => <option key={id} value={id}>{benchmarkLabel[id] ?? id}</option>)}
          </select>
        </div>
      </div>

      <div className={styles.quick} role="group" aria-label="Show">
        {shows.map((show) => (
          <button key={show} type="button" aria-pressed={filters.show === show} title={showHint[show]} onClick={() => update({ show })}>
            {showLabel[show]} <b>{counts[show]}</b>
          </button>
        ))}
      </div>

      <div className={styles.summary} ref={listRef}>
        <p role="status">
          {rows.length === 0
            ? 'No prompts match.'
            : <>Showing <b>{(page - 1) * pageSize + 1}–{(page - 1) * pageSize + shown.length}</b> of {filtered ? 'the ' : ''}<b>{rows.length}</b> {filtered ? 'matching ' : ''}{rows.length === 1 ? 'prompt' : 'prompts'}{filtered ? ` (${data.prompts.length} in all)` : ''}. The router ({priorityLabel[filters.priority].toLowerCase()}) got <b>{routerRight}</b> of them right.</>}
        </p>
        <Legend />
      </div>

      {rows.length === 0 ? (
        <Empty icon={<SearchX size={22} />} title="No prompts match these filters">
          <Button size="sm" onClick={() => replaceRoute(listHref({ ...filters, task: 'all', bench: 'all', show: 'all', q: '', page: 1 }))}>Clear the filters</Button>
        </Empty>
      ) : (
        <div className={styles.listBox}>
          <div className={styles.listHead} aria-hidden="true">
            <span>Prompt</span>
            <StripHead models={models} />
            <span>Router · {priorityLabel[filters.priority]}</span>
          </div>
          <ul className={styles.list} aria-label="Prompts">
            {shown.map((prompt) => (
              <li key={prompt.sample_id} className={styles.row}>
                <div className={styles.rowMain}>
                  <div className={styles.rowMeta}>
                    <span className={styles.bench}>{benchmarkLabel[prompt.benchmark] ?? prompt.benchmark}</span>
                    {prompt.category && <span>{prompt.category}</span>}
                    <code>{prompt.sample_id}</code>
                  </div>
                  <Link to={promptHref(prompt.sample_id, current)} className={styles.rowLink}>{excerpt(prompt)}</Link>
                </div>
                <OutcomeStrip prompt={prompt} models={models} pick={routerPick(prompt, filters.priority)} priority={filters.priority} />
                <RouterPick prompt={prompt} models={models} priority={filters.priority} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {pageCount > 1 && (
        <nav className={styles.pager} aria-label="Pages of prompts">
          <Button size="sm" onClick={() => goTo(page - 1)} disabled={page <= 1}><ChevronLeft size={14} />Previous</Button>
          <span>Page {page} of {pageCount}</span>
          <Button size="sm" onClick={() => goTo(page + 1)} disabled={page >= pageCount}>Next<ChevronRight size={14} /></Button>
        </nav>
      )}
      <PoolNote data={data} />
    </>
  )
}

/** One prompt: its text, the expected answer, every model's outcome, and who chose which model. */
export function PromptPage({ id }: { id: string }) {
  const { query } = useRoute()
  const filters = readFilters(query)
  const primary = usePrompts(filters.set)
  const here = primary.data?.prompts.find((item) => item.sample_id === id)
  // A link without its prompt set: look in the other set before giving up.
  const fallback = usePrompts(filters.set === 'final' ? 'cp3_test' : 'final', primary.isFetched && !here)
  const there = fallback.data?.prompts.find((item) => item.sample_id === id)
  const data = here ? primary.data : there ? fallback.data : undefined
  const prompt = here ?? there
  const texts = useSearchTexts(data)

  if (primary.isLoading || fallback.isLoading) return <div style={{ paddingTop: '3rem' }}><Skeleton height={480} /></div>
  if (!data || !prompt) {
    return (
      <div style={{ paddingTop: '3rem' }}>
        <Empty icon={<SearchX size={22} />} title="Prompt not found">
          <span>No prompt has the ID <code>{id}</code>. <Link to={listHref(filters)}>Back to every prompt</Link></span>
        </Empty>
      </div>
    )
  }

  const list = { ...filters, set: data.evaluation }
  const inList = filterPrompts(data.prompts, data.models, list, texts)
  const sequence = inList.some((item) => item.sample_id === id) ? inList : data.prompts
  const at = sequence.findIndex((item) => item.sample_id === id)
  const previous = sequence[at - 1]
  const next = sequence[at + 1]
  const models = data.models
  const byId = new Map(models.map((model) => [model.model_id, model]))
  const strategies = [...data.strategies].sort((a, b) => strategyRank(a) - strategyRank(b))
  const rows = models
    .map((model) => {
      const outcome = prompt.outcomes[model.model_id]
      return { model, outcome, verdict: verdictOf(outcome), chosenBy: strategies.filter((strategy) => prompt.choices[strategy] === model.model_id) }
    })
    .sort((a, b) => verdictRank[a.verdict] - verdictRank[b.verdict] || (a.outcome?.cost_usd ?? 0) - (b.outcome?.cost_usd ?? 0) || (a.outcome?.latency_ms ?? 0) - (b.outcome?.latency_ms ?? 0))
  const right = rows.filter((row) => row.verdict === 'right')
  const cheapest = right[0]
  const fastest = [...right].sort((a, b) => (a.outcome?.latency_ms ?? 0) - (b.outcome?.latency_ms ?? 0))[0]
  const bench = benchmarkLabel[prompt.benchmark] ?? prompt.benchmark
  const expectedIndex = prompt.expected_answer && prompt.options.length ? prompt.expected_answer.charCodeAt(0) - 65 : -1
  const frozen = models.filter((model) => !model.added_from).length

  return (
    <>
      <nav className={pages.crumbs} aria-label="Breadcrumb"><Link to={listHref(list)}>Prompts</Link><ChevronRight size={14} /><span>{prompt.sample_id}</span></nav>
      <header className={styles.hero}>
        <div className={styles.heroText}>
          <div className={pages.row}>
            <Badge>{evaluationLabel[data.evaluation].title}</Badge>
            <Badge>{taskLabel[prompt.task_group] ?? prompt.task_group} · {bench}</Badge>
            {prompt.category && <Badge>{prompt.category}</Badge>}
          </div>
          <h1>{taskLabel[prompt.task_group] ?? prompt.task_group} prompt from {bench}</h1>
          <p className={styles.heroMeta}><code>{prompt.sample_id}</code> · {prompt.dataset}, item {prompt.source_id}</p>
        </div>
        <nav className={styles.stepper} aria-label="Other prompts">
          {previous ? <ButtonLink size="sm" to={promptHref(previous.sample_id, list)}><ChevronLeft size={14} />Previous</ButtonLink> : <Button size="sm" disabled><ChevronLeft size={14} />Previous</Button>}
          <span>{at + 1} of {sequence.length}</span>
          {next ? <ButtonLink size="sm" to={promptHref(next.sample_id, list)}>Next<ChevronRight size={14} /></ButtonLink> : <Button size="sm" disabled>Next<ChevronRight size={14} /></Button>}
        </nav>
      </header>

      <div className={styles.detailGrid}>
        <section className={styles.promptCard} aria-labelledby="prompt-text">
          <h2 id="prompt-text" className={styles.cardLabel}>The prompt</h2>
          {prompt.task_group === 'code'
            ? <pre className={styles.code} tabIndex={0} aria-label="Prompt text"><code>{prompt.question}</code></pre>
            : <p className={styles.question}>{prompt.question}</p>}
          {prompt.options.length > 0 && (
            <ol className={styles.options} aria-label="Options">
              {prompt.options.map((option, index) => (
                <li key={optionLetter(index)} className={styles.option} data-expected={index === expectedIndex ? '' : undefined}>
                  <b>{optionLetter(index)}</b><span>{option}</span>
                  {index === expectedIndex && <span className={styles.verdict} data-verdict="right"><Check size={13} strokeWidth={2.5} aria-hidden="true" />Expected</span>}
                </li>
              ))}
            </ol>
          )}
          <div className={styles.expected}>
            <span className={styles.cardLabel}>Expected answer</span>
            {prompt.expected_answer
              ? <strong>{prompt.expected_answer}{expectedIndex >= 0 && prompt.options[expectedIndex] ? <small>{prompt.options[expectedIndex]}</small> : null}</strong>
              : <p>{prompt.answer_note ?? 'This prompt has no stored reference answer.'}</p>}
          </div>
        </section>
        <div className={styles.facts}>
          <Stat label="Models right" value={`${right.length} of ${models.length}`}
            hint={right.length === 0 ? 'No model answered this one right' : right.length === 1 ? `Only ${plainName(right[0].model.display_name)}` : right.length === models.length ? 'Every model answered it right' : `${models.length - right.length} wrong or failed`} />
          <Stat label="Cheapest right answer" value={cheapest?.outcome ? usd(cheapest.outcome.cost_usd) : '—'}
            hint={cheapest?.outcome ? `${plainName(cheapest.model.display_name)}, ${seconds(cheapest.outcome.latency_ms)}` : 'No right answer'} />
          <Stat label="Fastest right answer" value={fastest?.outcome ? seconds(fastest.outcome.latency_ms) : '—'}
            hint={fastest?.outcome ? `${plainName(fastest.model.display_name)}, ${usd(fastest.outcome.cost_usd)}` : 'No right answer'} />
        </div>
      </div>

      <Section id="prompt-router" title="Where the router sent it" description={`The adaptive router's choice under each priority, and how that model did. It chooses among the ${frozen} models it was trained with.`}>
        <div className={styles.picks}>
          {priorityOrder.map((priority) => {
            const pick = prompt.choices[`learned:${priority}`]
            const outcome = pick ? prompt.outcomes[pick] : undefined
            const model = pick ? byId.get(pick) : undefined
            return (
              <div key={priority} className={styles.pickCard}>
                <span className={styles.pickPriority}>{priorityLabel[priority]}</span>
                {pick ? (
                  <>
                    <Link to={modelHref(pick)} className={styles.pickCardModel}><ModelLogo id={pick} size={20} local={model?.access === 'local'} /><span>{nameOf(model, pick)}</span></Link>
                    <VerdictMark verdict={verdictOf(outcome)} />
                    {outcome && <span className={styles.pickFacts}>{seconds(outcome.latency_ms)} · {usd(outcome.cost_usd)}</span>}
                  </>
                ) : <span className={ui.muted}>No choice recorded</span>}
              </div>
            )
          })}
        </div>
      </Section>

      <Section id="prompt-models" title="How every model did" description="Right answers first, cheapest first. A strategy's badge sits beside the model it chose; the hindsight oracle shows the best choice given every outcome.">
        <div className={ui.tableWrap}>
          <table className={ui.table} aria-label="Every model on this prompt">
            <thead><tr><th>Model</th><th>Result</th><th>Time</th><th>Billed cost</th><th>Chosen by</th></tr></thead>
            <tbody>
              {rows.map(({ model, outcome, verdict, chosenBy }) => (
                <tr key={model.model_id}>
                  <td>
                    <Link to={modelHref(model.model_id)} className={styles.modelLink}>
                      <ModelLogo id={model.model_id} size={18} local={model.access === 'local'} />
                      <span className={styles.modelName}>{plainName(model.display_name)}</span>
                      <span className={styles.modelSub}>{makerOf(model.model_id).name}{model.access ? ` · ${accessLabel[model.access] ?? model.access}` : ''}{model.added_from ? ` · ${addedLabel[model.added_from] ?? 'Added'}` : ''}</span>
                    </Link>
                  </td>
                  <td><VerdictMark verdict={verdict} detail={verdict === 'failed' && outcome ? statusLabel[outcome.status] ?? outcome.status : undefined} /></td>
                  <td className={ui.num}>{outcome ? seconds(outcome.latency_ms) : '—'}</td>
                  <td className={ui.num}>{outcome ? usd(outcome.cost_usd) : '—'}</td>
                  <td>
                    {chosenBy.length
                      ? <span className={styles.badges}>{chosenBy.map((strategy) => <Badge key={strategy} tone={strategyFamily(strategy) === 'learned' ? 'accent' : 'neutral'} title={strategyLabel(strategy)}>{shortStrategy(strategy)}</Badge>)}</span>
                      : <span className={ui.muted}>—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <PoolNote data={data} />
      </Section>
    </>
  )
}
