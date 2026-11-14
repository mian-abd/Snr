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
- The app is now a public research site with light and dark themes: **Home**, **Router** (with a stress-test panel and a notice naming where a prompt would be sent), **Models** (catalog and a page per model), **Research** (results, significance, errors, robustness, downloads), **FAQ**, and **Lab** (the earlier rule-based tools).

See the [week of November 19](docs/checkpoint-4-progress.md).

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
