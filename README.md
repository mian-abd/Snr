# Adaptive LLM Router

Adaptive LLM Router is a local, reproducible console for comparing pinned OpenRouter models and making transparent routing decisions. Checkpoint 1 established the measurement evidence; Checkpoint 2 adds an inspectable rule-based policy and an offline strategy replay over that same saved evidence.

## Checkpoint 1 features

- Compare the same prompt across two pinned models.
- Inspect response text, latency, token usage, cost, and normalized failures.
- Filter the registry by a minimum context requirement.
- Run or resume a fixed 24-cell GSM8K experiment.
- Review sanitized, append-only experiment evidence.
- Use a single production URL served by FastAPI.

## Checkpoint 2 features

- Route one prompt to a single eligible pinned model using a visible priority: balanced, lower cost, higher quality, or faster response.
- Keep hard capability requirements separate from soft user priorities.
- Choose between the preserved Checkpoint 1 free pool and a dated three-model paid pool (Gemma 4 26B, Mercury 3, Gemini 4 Argon) whose prices and context lengths are checked against the live catalog before any paid call.
- Verify each pool's policy against deterministic expected-versus-actual acceptance cases (5 free, 7 paid) without a provider call.
- Replay two fixed baselines and four policy variants over the committed 24-cell free matrix or the 36-cell paid matrix, without making another provider call.
- Compare selected-model counts, accuracy, availability, median and p95 latency, total cost, and cost per correct answer, and inspect the model chosen for every prompt and why.
- Collect the paid matrix with `uv run --project backend python -m app.benchmarks.paid_matrix`, which prints a worst-case cost estimate, enforces a $1 cap, and only spends with `--confirm`, or from the Benchmark tab, which shows the same estimate and requires **Confirm and start**.
- Use both pools on every tab: Compare sends one prompt to every model in the selected pool, Eligibility lists all five registry entries, and Benchmark shows either saved matrix.

Checkpoint 2 is deliberately a simple, rule-based policy—not a learned router or a claim of statistically conclusive model rankings.

## Checkpoint 3 (weeks of Oct 22 to Nov 12)

- A fixed 600-prompt suite (200 GSM8K, 200 MMLU-Pro, 100 HumanEval+, 100 MBPP+) built from pinned, checksummed sources, with a 60/20/20 train/validation/test split fixed before any model runs: `python -m app.benchmarks.prepare_suite`.
- An 11-model pool across 8 families and 5 access paths: paid OpenRouter, free OpenRouter, anonymous OVHcloud, Google AI Studio, NVIDIA NIM, and a local Ollama model (`data/registry/cp3-pool-2026-10-27.json`).
- A paced, resumable, spend-capped runner for the whole pool: `python -m app.benchmarks.suite_runner --smoke 2` (estimate) then `--confirm`.
- Coding answers scored by EvalPlus in a Docker container with no network: `python -m app.benchmarks.code_scoring` (needs Docker Desktop).
- Logistic regression and gradient-boosted trees predicting P(success | prompt, model), compared on the validation split, plus multi-objective routing replay: `python -m app.learned.train`.
- First results (9 models × 600 prompts, 2026-10-28): logistic regression beats gradient-boosted trees, but a simple model-by-task success rate predicts as well as either. Report: `data/learned/cp3-full-router-comparison.json`.
- Week of Nov 5:
  - logistic regression is selected on validation, refit on train + validation, and exported as plain numbers (`data/learned/cp3-router-model.json`);
  - the weight presets are tuned on validation per priority;
  - the router is tested once on the held-out split against the fixed baselines and the rule router, with accuracy-cost and accuracy-latency plots (`docs/figures/`, `python -m app.learned.plots`).
- The **Learned** tab routes a prompt with the learned router: priority presets or custom weights, a provider-free preview of every model's score, and a one-call live route. It also shows the held-out comparison charts, the tuned presets, the matrix, and the classifier comparison. The Route tab keeps the Checkpoint 2 rule policy.
- Week of Nov 12: a hindsight oracle per priority and an under- and over-routing analysis on the held-out split, in the same report and tab.
- Checkpoint 3 deck: [docs/presentations/Adaptive_LLM_Router_Checkpoint_3.pptx](docs/presentations/Adaptive_LLM_Router_Checkpoint_3.pptx). Backup demo recording: `docs/demo/checkpoint-3-backup-demo.webm`.

Run each command with `uv run --project backend` from the repository root. See [weeks of Oct 22 and Oct 29](docs/checkpoint-3-progress.md) and the [data provenance errata](docs/data-provenance-errata.md).

## Toward Checkpoint 4 (week of Nov 19)

- A fresh final held-out set of 300 prompts, drawn after the router was frozen and excluding every earlier prompt: `python -m app.benchmarks.prepare_final`, run with `python -m app.benchmarks.suite_runner --suite final --confirm`.
- The final evaluation of the frozen router on the Checkpoint 3 test split and the final set, with 95% bootstrap intervals, paired tests, the oracle gap, a per-task routing-error analysis with worked examples, and robustness scenarios for price, latency, reliability, availability, and user priorities: `python -m app.learned.final_eval`. Report: `data/learned/final-evaluation.json`.
- Results on the 300 fresh prompts: the best-quality setting got 282 right against 284 for always using the strongest model, for 17% less; the lowest-cost setting got 265 for $0.0034; and after Mercury 3 was retired, the live catalog check kept the fastest setting at 276 right instead of 83. Prompt-level features did not beat a per-task reference.
- A live catalog check at startup: models a provider no longer serves are excluded with the reason shown, and changed prices update expected costs (`python -m app.registry.live_catalog` prints it).
- Export of seven result tables as CSV or JSON, from the console or `python -m app.learned.export`.
- Flagship models (2026-11-14): GPT-6.1 Sol, Gemini 4 Carbon, and Kimi K3.1 Pro answered all 900 prompts; Grok 4.7 was stopped because its reasoning ran past the token limit and the $25 budget.
  - **Command:** `python -m app.benchmarks.suite_runner --pool flagship --spend-cap N --confirm` runs them.
  - **Study:** `python -m app.learned.pool_study --study flagship` fits a second router with the same recipe and compares it with the frozen one. Report: `data/learned/flagship-study.json`.
  - **Results:** GPT-6.1 Sol matches Gemini 4 Argon (284 of 300) for less than half the cost at a third of the time. With it, the fastest setting gets 284 right instead of 276 and is 1.3 s quicker (not significant after the Holm correction). Best quality does not improve (283 vs 282), and the expensive flagships are never chosen.
- The app is a public research site, redesigned on 2026-11-14 as a data-first leaderboard. It has light and dark themes and these pages:
  - **Home:** highlights and charts of accuracy, cost, and time per model;
  - **Router:** with a stress-test panel, a notice naming where a prompt would be sent, and a switch to the pool with the flagships;
  - **Models:** a sortable leaderboard table and a page per model;
  - **Research:** results, significance, the flagship study, errors, robustness, and downloads;
  - **FAQ**;
  - **Lab:** the earlier rule-based tools.

See the [week of November 19](docs/checkpoint-4-progress.md).

## Toward Checkpoint 4 (week of Nov 26, done Nov 20 and 21)

- Five more models on all 900 prompts: GPT-6 Luna, MiMo-V2.6 Flash, Muse Ember, Ministral 8B, and the free ERNIE 5.5 Flash (`data/registry/budget-pool-2026-11-20.json`, run with `--pool budget`).
- Pool studies: `python -m app.learned.pool_study --study flagship|wide --from-runs` adds dated registries to the frozen pool, refits the Checkpoint 3 recipe, and evaluates the new router against fixed questions. The wide study fits a third router on every model. Reports: `data/learned/flagship-study.json` and `data/learned/wide-study.json`.
- Results on the fresh prompts: GPT-6 Luna got 274 of 300 right for $0.047, the best of the budget models. A router fit on all 17 models got 270 right at lowest cost for $0.022 (the frozen router: 265 for $0.0034), 282 at best quality (the same), and 278 at fastest for $0.26 (the flagship router: 284 for $0.50). No fixed comparison is significant after the Holm correction. ERNIE 5.5 Flash's last 16 prompts ran on 2026-11-24, after the free daily quota reset; it joined the wide study without changing any of these numbers.
- Robustness and priority figures: `python -m app.learned.plots` (add `--slides` for dark versions).
- Data validation: `python -m app.learned.validate` checks every committed table, report, and router offline, and runs in CI. Column meanings and units are in the [data dictionary](docs/data-dictionary.md).
- Export of eleven tables, including four for the pool studies.
- Failure handling: when the chosen model still fails after its retry, the next-best eligible model answers once, and the page says so. One spend cap can now cover related runs (`--count-spend-from`).
- Site: a search palette (Ctrl+K), a model comparison page, interactive robustness and priority charts, score bars on Router, a pool switch with every model, a prompt explorer (`#/prompts`) showing every model's result on every prompt, and a restyled Lab. Backup demo recording: `docs/demo/checkpoint-4-backup-demo.webm`.

See the [week of November 26](docs/checkpoint-4-progress.md#week-of-november-26-robustness-figures-data-validation-failure-handling-more-models-interface).

## Checkpoint 4 (week of Dec 3)

- Deck: `docs/presentations/Adaptive_LLM_Router_Checkpoint_4.pptx` (10 slides, about 6 minutes).
- Demo guide: [docs/live-demo-guide.md](docs/live-demo-guide.md), organized by the four things the proposal promised for Checkpoint 4.
- ERNIE 5.5 Flash is complete: 254 of 300 fresh prompts right, never chosen. The wide study was rebuilt with 17 models and every headline number is unchanged.
- Scorer fix: EvalPlus reused an old `*_eval_results.json` when a run was resumed, so `app/benchmarks/code_scoring.py` now deletes it before every evaluation. An audit of all 66 results files found no earlier result affected.
- Gemma 4 26B A4B is now unavailable (its pinned host, NextBit, no longer serves it; found on 2026-11-26), the second real provider change after Mercury 3. The live catalog check handles it. On the standard pool, Fastest now picks Qwen 3.5 9B (local), and the stress test moves it to DeepSeek V4 Flash.

See the [week of December 3](docs/checkpoint-4-progress.md#week-of-december-3).

## Prerequisites

- Python 3.12 managed by [uv](https://docs.astral.sh/uv/)
- Node.js 24 and npm
- A replacement OpenRouter API key. Never reuse a key that has appeared in chat or source control.

## Setup

```powershell
Copy-Item .env.example backend/.env
# Add the replacement key to backend/.env only.
./scripts/bootstrap.ps1
```

Development:

```powershell
./scripts/dev.ps1
```

Production-style demo:

```powershell
./scripts/demo.ps1
```

The development UI runs at `http://localhost:5173`; the production-style demo runs at `http://localhost:8000`.

## Verification

```powershell
./scripts/check.ps1
```

The check script runs backend linting, type checks, tests, frontend tests, and a production frontend build. Tests never call a live model.

## Live benchmark safety

The runner validates the exact model IDs against the live OpenRouter catalog before making calls. It fails closed on model drift, uses one request at a time, records every attempt, and stops at the project-side daily budget. Manual comparisons are not saved unless the UI toggle is enabled.

See [full project context](CONTEXT.md), [Checkpoint 1](docs/checkpoint-1.md), [Checkpoint 2](docs/checkpoint-2.md), [build handover](docs/build-handover.md), [presentation script](docs/presentation-script.md), [live demo guide](docs/live-demo-guide.md), [research basis](docs/research-basis.md), and [demo script](docs/demo-script.md) for the protocol and limitations.

## License

MIT
