# Weeks of October 22 and October 29: learned-router groundwork

This records the proposal's work-plan items for the weeks of October 22 and October 29. The week of November 5 (choosing and integrating the learned router, finishing user weights, comparison plots, Checkpoint 3 materials) and everything after is deliberately not started.

| Proposal item | Status |
| --- | --- |
| Present Checkpoint 2 and document any routing or interface issues | Issues documented below |
| Build the train, validation, and test split | Done: `data/benchmarks/cp3_suite.jsonl` |
| Implement prompt and model feature extraction | Done: `backend/app/learned/features.py` |
| Begin training the first lightweight router models | Done: `backend/app/learned/train.py` |
| Prepare for the ethics discussion | Skipped at the owner's request |
| Train and compare logistic regression and gradient-boosted routing models | Done on the 9-model matrix: [results](#results-2026-10-28) |
| Implement the multi-objective scoring method | Done: `backend/app/routing/multi_objective.py` |
| Add tests for learned-router inputs and scoring | Done: `test_learned.py`, `test_multi_objective.py`, `test_suite.py`, `test_openai_compatible.py`, `test_code_scoring.py` |

## Checkpoint 2 routing and interface issues

1. **Free shared capacity dominated the Checkpoint 1 matrix.** Gemma's free route lost 9 of 12 calls to rate limits. Addressed with the dated paid pool, and now a multi-provider pool.
2. **Price drift.** OpenRouter raised paid Gemma 4 26B overnight (2026-10-23). The drift check correctly refused every paid call; a new dated snapshot fixed it.
3. **Only the Route tab used the paid models at first.** Compare, Eligibility, and Benchmark were extended to both pools on 2026-10-23.
4. **Empty and truncated responses.** Mercury 3 returned empty content on two Checkpoint 2 questions and runs past the token cap on some coding prompts. These are recorded as failures, never dropped.
5. **Local environment.** A sandboxed shell installed Python where the owner's own terminal could not see it, so `./scripts/demo.ps1` failed until Python 3.12.14 was installed from the owner's terminal. On this machine Windows Application Control also blocks the `mypy.exe` launcher, so the check script now runs `python -m mypy`.
6. **mypy configuration was not applied.** The check script and CI ran mypy from the repository root, where `backend/pyproject.toml` (strict mode, the pydantic plugin) is not found. Both now pass `--config-file backend/pyproject.toml`; strict mode passes on all modules.
7. **Benchmark provenance.** The GSM8K revision and checksum recorded in Checkpoints 1 and 2 cannot be verified. The questions are genuine. See `docs/data-provenance-errata.md`.

## The Checkpoint 3 benchmark suite

`uv run --project backend python -m app.benchmarks.prepare_suite` rebuilds it byte for byte.

| Benchmark | Source (pinned) | Sampled | Train / validation / test |
| --- | --- | ---: | --- |
| GSM8K (math) | `openai/gsm8k` test, commit `740312a`, SHA-256 `ee7b8da9…` | 200 of 1,319 (Checkpoint 1's 12 excluded) | 120 / 40 / 40 |
| MMLU-Pro (QA) | `TIGER-Lab/MMLU-Pro` test, commit `b189ec7`, SHA-256 `0e24a191…` | 200 of 12,032, stratified over 14 categories | 120 / 40 / 40 |
| HumanEval+ (code) | EvalPlus release v0.1.10, SHA-256 `272720b9…` | 100 of 164 | 60 / 20 / 20 |
| MBPP+ (code) | EvalPlus release v0.2.0, SHA-256 `af43697e…` | 100 of 378 | 60 / 20 / 20 |

- Seed 2026; the split is stratified per benchmark and fixed before any model ran, as the proposal requires.
- The 12 Checkpoint 1 questions are excluded because the rule router's thresholds were designed while looking at them.
- Prompts (`backend/app/benchmarks/tasks.py`, version `cp3-v2`):
  - GSM8K uses the Checkpoint 1 template.
  - MMLU-Pro is zero-shot chain of thought ending in "The answer is (X)", scored with the official extraction order restricted to the offered letters. A failed extraction is wrong, not a random guess as in the official script.
  - Code uses EvalPlus's chat instruction.
- Token caps: 2,048 for math, 4,096 for QA and code, chosen so only runaway generations hit them.
  - The first full attempt (`cp3-v1`, 1,024 / 2,048 / 2,048) was stopped after 7 minutes and $0.61. Reasoning-by-default models were running out of tokens on ordinary questions: DeepSeek V4 Flash on 14 GSM8K questions, Mercury 3 on 16 GSM8K and 30 MMLU-Pro. That measured default reasoning length rather than ability and would have skewed the success labels.
  - Every model was re-run under the new caps; raising them only for failed cells would bias the comparison.
  - The partial run is kept locally as `data/local/cp3/cp3-aborted-caps-1024-2048`.
- Temperature 0, 180 s timeout.

## The multi-provider model pool

Pool file: `data/registry/cp3-pool-2026-10-27.json`, built by `app.registry.build_pool`. The owner asked for free and open-source models beyond OpenRouter; three research passes on 2026-10-27 checked providers, OpenRouter's free models, and local options against live docs and APIs.

| Model | Family | Access | How |
| --- | --- | --- | --- |
| Gemma 4 26B A4B | Google | paid | OpenRouter, pinned to NextBit (bf16) |
| Mercury 3 | Inception (diffusion) | paid | OpenRouter, Inception |
| Gemini 4 Argon | Google | paid | OpenRouter, pinned to Google AI Studio |
| DeepSeek V4 Flash | DeepSeek | paid | OpenRouter, limited to three fp8 hosts |
| Nemotron 3 Ultra 550B | NVIDIA | free | OpenRouter free (1,000 requests/day per account) |
| gpt-oss-120b | OpenAI (open weights) | free | OVHcloud AI Endpoints, anonymous, no signup |
| Llama 3.3 70B | Meta | free | OVHcloud anonymous |
| Qwen 3.8 27B | Alibaba | free | OVHcloud anonymous |
| Gemma 4 31B | Google | free | Google AI Studio free tier (needs `GEMINI_API_KEY`) |
| DeepSeek V4.1 Flash | DeepSeek | free | NVIDIA NIM (needs `NVIDIA_API_KEY`) |
| Qwen 3.5 9B | Alibaba | local | Ollama on this laptop's RTX 5060 |

Gemma 4 31B and DeepSeek V4.1 Flash are not in the 2026-10-28 matrix: both free services were overloaded when tested (see [the keyed models](#the-two-keyed-models)).

Research findings that shaped the pool:

- The free-provider list the proposal cites (`cheahjs/free-llm-api-resources`) has returned 404 since August 2026; an archived copy plus each provider's docs were used.
- Ruled out: GitHub Models (retired 2026-07-30), Together and Hugging Face (no longer free), Cerebras (needs a card), Groq free tier (200K tokens/day, about 220 prompts/day per model), SambaNova (20 requests/day), and Cohere (1,000 calls/month).
- Excluded OpenRouter free models: agent-only Inkling, the Poolside models expiring 2026-10-31, a Nemotron Nano endpoint with 8.7% uptime, and the auto-selecting `openrouter/free`.
- Reproducibility: OpenRouter hosts are pinned with `allow_fallbacks: false`, and each result records the host that served it. Dated model IDs are used everywhere; no `-latest` aliases.

`backend/app/providers/openai_compatible.py` reaches every model through its OpenAI-compatible API, one attempt per call, with the same normalized statuses, served-model checks, and cost handling as the Checkpoint 1 adapter. Keys come from `backend/.env` and are never stored in results.

## Running the matrix

`uv run --project backend python -m app.benchmarks.suite_runner --confirm --run-id cp3-full`

- Each model runs in its own paced worker (OVHcloud about 1.8 starts per minute with two in flight; OpenRouter free 18 per minute).
- Every attempt is appended immediately, and runs resume where they stopped.
- At most one retry, with backoff for rate limits.
- Paid spend has a hard $15 cap enforced against actual spend plus in-flight calls, and OpenRouter free calls stop at 950 a day.
- A smoke test (2 prompts per benchmark per model) found a rate-limited single DeepSeek host and truncation at the original token caps; both were fixed before the full run.

Code answers are scored by `app.benchmarks.code_scoring` inside `ganler/evalplus:v0.3.1`, pinned by digest (`sha256:26b11809…`), with no network, an 8 GB memory cap, 4 CPUs, a 512-process limit, no new privileges, and all capabilities dropped. A task passes only if the base and extra tests both pass.

- Because the container has no network, EvalPlus reads the same pinned, checksum-verified dataset files the suite was built from, mounted read-only and passed through `HUMANEVAL_OVERRIDE_PATH` and `MBPP_OVERRIDE_PATH`. Their versions match the image's defaults (v0.1.10 and v0.2.0).
- Docker Desktop 4.97 runs on WSL 2, installed on 2026-10-28.

## The learned router and multi-objective scoring

- **Labels:** success means the call was served and the answer was correct (exact numeric match, correct letter, or EvalPlus base + extra pass). Failed calls count as failures.
- **Features:** task group, length, numbers, lines, sentences, options, code markers, and the rule router's visible signals (`backend/app/learned/features.py`). Model features: identity, model × task interactions, price, local / free flags, and median latency, output length, and success rate from **training rows only**, leaving the row's own prompt out.
- **Classifiers:** logistic regression (standardized, C in {0.01, 0.1, 1, 10}) and histogram gradient-boosted trees (depth 2 or 3, learning rate 0.05 or 0.1, 100 or 300 iterations, L2 1.0). Each family's setting is chosen by validation log loss, and the train-to-validation gap is reported as the overfitting check.
- **Multi-objective scoring** (`backend/app/routing/multi_objective.py`):
  - score = quality × P(success) − cost × normalized expected cost − latency × normalized expected latency − reliability × failure rate.
  - Hard requirements are applied first.
  - Cost and latency are divided by the largest eligible value, so ratios between models survive.
  - Each priority has a weight preset; the emphasized objective is 0.5, not 1.0, so a model expected to fail can't win just by being cheap. A test covers that case.
- **Validation replay:** each validation prompt is routed per priority and compared with fixed cheapest, fixed strongest, and the rule router, reporting accuracy, cost, cost per correct answer, and median and p95 latency.
- **Test split:** never read. It is reserved for Checkpoint 3's held-out evaluation.

`uv run --project backend python -m app.learned.train --run-id cp3-full` writes `data/learned/cp3-full-router-comparison.json`.

## Results (2026-10-28)

### The matrix

9 models × 600 prompts = 5,400 cells, run `cp3-full` (2026-10-27 to 2026-10-28). Raw responses stay in `data/local/cp3/cp3-full`, which git ignores; the comparison report is committed.

| Model | Access | GSM8K | MMLU-Pro | Code | Total of 600 | Median latency | Failed calls |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Gemini 4 Argon | paid | 193 | 185 | 185 | 563 | 5.4 s | 1 malformed |
| Gemma 4 26B | paid | 191 | 162 | 164 | 517 | 5.0 s | 0 |
| Nemotron 3 Ultra | free (OpenRouter) | 182 | 159 | 170 | 511 | 12.6 s | 5 malformed or empty |
| DeepSeek V4 Flash | paid | 182 | 158 | 168 | 508 | 5.2 s | 41 truncated |
| gpt-oss-120b | free (OVH) | 191 | 154 | 150 | 495 | 16.2 s | 2 truncated, 1 timeout |
| Mercury 3 | paid | 183 | 160 | 151 | 494 | 1.3 s | 71 truncated |
| Llama 3.3 70B | free (OVH) | 187 | 153 | 153 | 493 | 16.0 s | 0 |
| Qwen 3.5 9B | local | 189 | 153 | 129 | 471 | 6.6 s | 0 |
| Qwen 3.8 27B | free (OVH) | 181 | 144 | 136 | 461 | 23.8 s | 56 timeouts, 48 truncated |

- Each column has 200 prompts; code is 100 HumanEval+ plus 100 MBPP+ tasks (base and extra tests). Every failed call counts as wrong.
- "Truncated" means the answer reached the token cap (2,048 math, 4,096 QA and code) without finishing, which is runaway generation at these caps.
- Qwen 3.8's timeouts come from the anonymous OVH endpoint (p95 latency 142 s against a 180 s limit), not from the model.
- Every served paid call came from its pinned host. DeepSeek: 558 Parasail, 1 Crusoe.
- Qwen 3.5 9B (Q4_K_M) runs with thinking disabled (`reasoning_effort: "none"`), 88% on the laptop's RTX 5060 at about 50 tokens per second. Every other model uses its provider's default reasoning, so this row measures a non-thinking configuration.

**Spend.**
- Recorded paid spend: $2.61 for `cp3-full` (Gemini 4 Argon $2.29, Mercury 3 $0.12, DeepSeek V4 Flash $0.11, Gemma 4 26B $0.08), and $3.32 across all Checkpoint 3 runs including smoke tests and the abandoned `cp3-v1` attempt.
- Until 2026-10-28 the adapter recorded truncated and empty answers as $0, although providers bill them. The unrecorded amount is at most $0.16 for `cp3-full` and $0.07 for `cp3-v1` (estimated at the full token cap), so true spend is between $3.32 and $3.55.
- The adapter now keeps usage and cost on those answers, with a test. The replay's expected cost for Mercury 3 and DeepSeek is slightly low for the same reason.

### Classifier comparison (validation split)

Training rows: 3,240 (360 prompts × 9 models). Validation rows: 1,080 (120 prompts × 9 models).

| Predictor | Chosen setting | Log loss | Brier | ROC AUC | Train-to-validation gap |
| --- | --- | ---: | ---: | ---: | ---: |
| Logistic regression | C = 0.01 | 0.467 | 0.150 | 0.696 | 0.085 |
| Gradient-boosted trees | depth 2, rate 0.05, 100 iterations | 0.491 | 0.157 | 0.646 | 0.174 |
| Reference: model × task success rate | none | 0.454 | 0.146 | 0.697 | — |

- **Logistic regression beats the boosted trees** on every validation metric and overfits half as much. The trees' best setting was the smallest in the grid; larger ones overfit more.
- **The reference does slightly better than both.** It predicts each model's training success rate on the prompt's task group, with add-one smoothing and no prompt features. With 360 training prompts, the prompt features do not yet add predictive signal beyond knowing which model is good at which task.
- Logistic regression's chosen C is the strongest regularization in the grid, which points the same way.
- This is reported as found. Choosing and integrating the learned router is a week-of-November-5 item.

### Routing replay (120 validation prompts)

Each strategy routes every validation prompt to one model and is scored by that model's saved outcome.

| Strategy | Correct | Cost | Median latency | p95 latency | Models picked |
| --- | ---: | ---: | ---: | ---: | --- |
| Always Gemma 4 26B (cheapest paid) | 99 | $0.016 | 5.0 s | 13.2 s | Gemma 4 26B 120 |
| Always Gemini 4 Argon (strongest) | 110 | $0.519 | 5.4 s | 13.9 s | Gemini 4 Argon 120 |
| Checkpoint 2 rule router | 102 | $0.136 | 3.9 s | 10.2 s | Mercury 3 57, Gemma 36, Gemini 27 |
| Logistic regression, cost | 101 | $0.008 | 8.3 s | 49.4 s | Nemotron 40, Gemma 40, gpt-oss 33, Qwen 3.5 9B 7 |
| Logistic regression, quality | 110 | $0.474 | 5.2 s | 13.9 s | Gemini 92, Gemma 28 |
| Logistic regression, latency | 109 | $0.260 | 4.2 s | 12.4 s | Gemini 54, Mercury 53, Gemma 13 |
| Logistic regression, balanced | 99 | $0.018 | 5.0 s | 14.7 s | Gemma 100, DeepSeek 20 |
| Boosted trees, cost | 89 | $0.000 | 7.0 s | 85.6 s | Qwen 3.5 9B 120 |
| Boosted trees, quality | 99 | $0.372 | 6.0 s | 29.9 s | Qwen 3.5 9B 70, Gemini 50 |
| Boosted trees, latency | 94 | $0.058 | 2.6 s | 12.9 s | Mercury 72, Qwen 3.5 9B 39, Gemini 5, Gemma 4 |
| Boosted trees, balanced | 92 | $0.009 | 4.0 s | 12.9 s | Qwen 3.5 9B 80, Mercury 37, Gemma 3 |
| Reference, cost | 101 | $0.008 | 8.4 s | 49.4 s | gpt-oss 40, Nemotron 40, Gemma 40 |
| Reference, quality | 110 | $0.445 | 6.4 s | 19.9 s | Gemini 80, gpt-oss 40 |
| Reference, latency | 110 | $0.448 | 5.1 s | 13.9 s | Gemini 80, Gemma 40 |
| Reference, balanced | 98 | $0.020 | 5.1 s | 15.0 s | Gemma 80, DeepSeek 40 |

- Logistic regression's quality priority matches always-strongest (110 of 120) for 9% less. Its latency priority gets 109 for half the cost, with lower latency.
- Logistic regression's cost priority beats always-cheapest (101 against 99) for half the cost, but it routes to free models, so the slowest 5% of calls take about 49 s.
- The boosted trees overrate the local Qwen 3.5 9B and lose 10 to 20 prompts.
- The reference routes as well as logistic regression.
- With 120 prompts, differences of one to three correct answers are within noise.

### The two keyed models

Both keys authenticate, but both free services were overloaded on 2026-10-28, so neither model has run the full suite. Smoke tests used 2 prompts per benchmark, 8 per model.

| Model | Morning | Afternoon |
| --- | --- | --- |
| Gemma 4 31B (Google AI Studio) | 3 of 8 answered; mostly HTTP 500 and 503 | 6 of 8 answered, 50–80 s each |
| DeepSeek V4.1 Flash (NVIDIA NIM) | 2 of 8 answered; 180 s timeouts | 4 of 8 answered, 112–149 s each |

- AI Studio returns Gemma's reasoning inline as a leading `<thought>…</thought>` block, and rejects `reasoning_effort` for Gemma. Scoring the raw text could pick up a letter or number from the reasoning, so the adapter removes that block before scoring, with tests.
- AI Studio's `completion_tokens` excludes those reasoning tokens.
