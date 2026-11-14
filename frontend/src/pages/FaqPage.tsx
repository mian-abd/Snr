import { HelpCircle, Plus } from 'lucide-react'
import type { ReactNode } from 'react'
import type { EvaluationSet, LearnedMatrixRow } from '../api/types'
import { evaluationOf, find, useCatalog, useFinalReport, useLearnedReport } from '../lib/data'
import { pct, usd } from '../lib/format'
import { Link } from '../lib/Link'
import { PageHeader } from '../ui'
import styles from './pages.module.css'

const taskNames: Record<string, string> = { math: 'math word problems', qa: 'multiple-choice knowledge questions', code: 'writing Python functions' }

function bestFor(matrix: LearnedMatrixRow[], task: string) {
  const rate = (row: LearnedMatrixRow) => (row.prompts_by_task[task] ? row.correct_by_task[task] / row.prompts_by_task[task] : 0)
  const ranked = [...matrix].filter((row) => row.prompts_by_task[task]).sort((a, b) => rate(b) - rate(a))
  const top = ranked[0]
  const freeNearTop = ranked.find((row) => row.access !== 'paid' && rate(top) - rate(row) <= 0.05)
  return top ? { top, rate: rate(top), free: freeNearTop, freeRate: freeNearTop ? rate(freeNearTop) : 0 } : null
}

function Q({ q, children, open }: { q: string; children: ReactNode; open?: boolean }) {
  return (
    <details open={open}>
      <summary>{q}<Plus size={18} /></summary>
      <div className={styles.faqBody}>{children}</div>
    </details>
  )
}

function savings(evaluation: EvaluationSet | undefined) {
  const lq = evaluation && find(evaluation.strategies, 'learned:quality')
  const fs = evaluation && find(evaluation.strategies, 'fixed_strongest')
  const comparison = evaluation?.comparisons.find((item) => item.strategy_id === 'learned:quality' && item.baseline_id === 'fixed_strongest')
  const total = lq && fs ? fs.total_cost_usd - lq.total_cost_usd : 0
  // The task where the best-quality priority saves the most against always using the strongest model.
  const main = lq && fs && total > 0
    ? Object.entries(fs.by_task)
        .map(([task, strongest]) => ({ task, strongest, routed: lq.by_task[task], saved: strongest.total_cost_usd - (lq.by_task[task]?.total_cost_usd ?? 0) }))
        .filter((item) => item.routed)
        .sort((a, b) => b.saved - a.saved)[0]
    : undefined
  return { lq, fs, comparison, main, share: main ? main.saved / total : 0 }
}

const shareWords = (share: number) => (share >= 0.9 ? 'Almost all' : share >= 0.5 ? 'Most' : 'The largest part')

export function FaqPage() {
  const report = useFinalReport()
  const learned = useLearnedReport()
  const catalog = useCatalog()
  const fresh = evaluationOf(report.data, 'final') ?? evaluationOf(report.data, 'cp3_test')
  const matrix = fresh?.matrix.filter((row) => row.prompts - row.failed_calls > 0) ?? learned.data?.matrix ?? []
  const { lq, fs, comparison, main, share } = savings(fresh)
  const features = fresh?.comparisons.find((item) => item.strategy_id === 'learned:quality' && item.baseline_id === 'model_task_prior:quality')
  const featuresReal = features ? features.holm_p < 0.05 : false
  const ll = fresh && find(fresh.strategies, 'learned:latency')
  const ln = fresh && find(fresh.strategies, 'learned_no_catalog:latency')
  const retired = catalog.data?.models.filter((item) => !item.available) ?? []
  const oracle = fresh?.oracle.find((item) => item.strategy_id === 'oracle:quality')

  return (
    <>
      <PageHeader
        eyebrow={<><HelpCircle size={15} />Questions</>}
        title="Frequently asked questions"
        description="Straight answers, computed from the published results wherever a number is involved."
      />
      <div className={styles.faq}>
        <Q q="What does the adaptive router do?" open>
          <p>For each prompt, it estimates how likely every available model is to answer correctly, then picks the model with the best balance of that chance, its price, and its speed for the priority you chose. It never splits a prompt across models and never secretly swaps in a different model: you see the choice and the reason before anything is sent.</p>
          <p>Try it on the <Link to="/router">Router</Link> page. Previews are free and private.</p>
        </Q>

        <Q q="Which model is best for math, knowledge questions, or code?">
          {matrix.length ? (
            <ul>
              {['math', 'qa', 'code'].map((task) => {
                const best = bestFor(matrix, task)
                if (!best) return null
                return (
                  <li key={task}>
                    For <strong>{taskNames[task]}</strong>, {best.top.display_name} was most accurate ({pct(best.rate, 0)}).
                    {best.free && best.free.model_id !== best.top.model_id && ` ${best.free.display_name}, which is free, came within five points (${pct(best.freeRate, 0)}).`}
                  </li>
                )
              })}
            </ul>
          ) : <p>The results are not loaded yet.</p>}
          <p>Measured on {fresh?.prompts ?? 'the'} fresh prompts. See every model on the <Link to="/models">Models</Link> page.</p>
        </Q>

        <Q q="How much money does routing save?">
          {lq && fs ? (
            <p>Going for the best quality, the router answered {lq.correct} of {lq.prompts} fresh prompts correctly for {usd(lq.total_cost_usd)}. Sending everything to the strongest model got {fs.correct} right for {usd(fs.total_cost_usd)}: about {Math.round((1 - lq.total_cost_usd / Math.max(fs.total_cost_usd, 1e-9)) * 100)}% less spent for {lq.correct >= fs.correct ? 'the same or better' : 'slightly lower'} accuracy.{comparison && ` The accuracy difference is ${comparison.holm_p < 0.05 ? 'statistically significant' : 'within the noise'} (adjusted p = ${comparison.holm_p.toFixed(2)}).`}</p>
          ) : <p>The results are not loaded yet.</p>}
          {main && main.routed && (
            <p>{shareWords(share)} of the saving ({pct(share, 0)}) comes from {taskNames[main.task] ?? main.task}: there the router got {main.routed.correct} of {main.routed.prompts} right, against {main.strongest.correct} for the strongest model, for {usd(main.routed.total_cost_usd)} instead of {usd(main.strongest.total_cost_usd)}.</p>
          )}
        </Q>

        <Q q="Is the router smarter than just picking the right model per task?">
          {features ? (
            <p>
              {featuresReal ? 'Yes, measurably.' : 'Not measurably, on these benchmarks.'} A simpler router that knows each model's average accuracy per task, and nothing about the individual prompt, {featuresReal ? 'does worse' : 'does about as well'}. On the fresh prompts the full router got {features.correct} right against {features.baseline_correct} for the simple one{features.correct === features.baseline_correct ? '.' : featuresReal ? `, a real difference (adjusted p = ${features.holm_p.toFixed(3)}).` : ', a difference the data cannot distinguish from chance.'}
              {fresh?.classifier && fresh.reference_model_task_prior && ` Its probability estimates are slightly sharper (log loss ${fresh.classifier.log_loss.toFixed(3)} against ${fresh.reference_model_task_prior.log_loss.toFixed(3)}), but that rarely changes which model wins.`}
            </p>
          ) : <p>The results are not loaded yet.</p>}
          <p>Benchmark prompts within one task are similar to each other. The prompt-level features would matter more on varied real-world traffic, which is a limit of this study.</p>
        </Q>

        <Q q="What happens when a provider retires a model or changes its price?">
          <p>The server asks the providers' public catalogs what they serve, at startup and whenever you press "Check again" on the Models page. A model no provider serves any more is never chosen, with the reason shown; a new price updates the expected cost straight away. If the check fails, the dated snapshot is used.</p>
          {retired.length > 0 && <p>Right now {retired.map((item) => item.display_name).join(' and ')} {retired.length === 1 ? 'is' : 'are'} unavailable.{ll && ln && ` That really happened during this study: without the live check, the fastest priority kept sending prompts to the retired model and got ${ln.correct} of ${ln.prompts} right instead of ${ll.correct}.`}</p>}
        </Q>

        <Q q="Is my prompt sent anywhere or stored?">
          <p><strong>Preview never sends your prompt anywhere.</strong> Pressing Run sends it to exactly one provider: the page names which one, and its data policy, before you press it. Free endpoints may log prompts (NVIDIA's free tier may use them for training), OVHcloud says it stores nothing, and the local model runs entirely on this computer.</p>
          <p>This site does not save routed prompts or responses. Don't send personal or confidential text to a third-party model.</p>
        </Q>

        <Q q="How were answers graded?">
          <ul>
            <li><strong>Math (GSM8K):</strong> the final number must match the reference exactly.</li>
            <li><strong>Knowledge (MMLU-Pro):</strong> the chosen letter must match, out of up to ten options.</li>
            <li><strong>Code (HumanEval+, MBPP+):</strong> the function must pass the original and the extra hidden tests, run in a locked-down container with no network.</li>
          </ul>
          <p>A call that fails, times out, or returns nothing usable counts as wrong.</p>
        </Q>

        <Q q="How much can I trust these numbers?">
          <p>Every result comes with a 95% interval, found by resampling the prompts 10,000 times. Head-to-head questions use McNemar's exact test and a Holm correction, and the questions were written down before the fresh results came in. With a few hundred prompts, a difference of a handful of answers is usually noise; the <Link to="/research">Research</Link> page marks which differences are real.</p>
        </Q>

        <Q q="Why doesn't the router always pick the cheapest model?">
          <p>Because the cheapest model is wrong more often on some tasks. Each priority was tuned, on separate validation prompts, to stay at least as accurate as always using the cheapest paid model; the best-quality priority accepts a higher bill for more right answers. You can set your own weights under Advanced settings on the Router page.</p>
          {oracle && <p>With perfect hindsight, a router could have reached {oracle.correct} of {oracle.prompts} for {usd(oracle.total_cost_usd)}, so there is still room for better predictions.</p>}
        </Q>

        <Q q="What are the main limitations?">
          <ul>
            <li>Benchmarks are not real traffic, and "correct" is rarely a single number in practice.</li>
            <li>Cost and time are scored relative to the priciest and slowest available model, so a change to one model can shift choices among the others.</li>
            <li>The tuned priorities ignore reliability unless you raise its weight.</li>
            <li>The router only knows the models it was trained with.</li>
          </ul>
          <p>More in <Link to="/research?section=method">Method and limits</Link>.</p>
        </Q>

        <Q q="Can I reproduce the results?">
          <p>Yes. The prompt sets, every model's graded answer, every routing decision, and the router itself are published; the <Link to="/research?section=downloads">downloads</Link> are built from them. Rebuilding the full report from those files takes one command, <code>python -m app.learned.final_eval</code>, and no API keys.</p>
        </Q>
      </div>
    </>
  )
}
