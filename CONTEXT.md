# Adaptive LLM Router: technical context, build log, and handover

Last updated: 2026-10-22  
Current milestone: Checkpoint 2  
Repository: `https://github.com/mian-abd/Snr`  
Primary branch: `main`

## 1. Purpose of this document

This file is the durable operating record for the project. It combines the roles normally split across a contributor-instructions file, `context.md`, `log.md`, and `handover.md`:

- why the project exists and what it is trying to prove;
- what has been built, in implementation detail;
- the important design decisions and why they were made;
- exact data, model, benchmark, and API contracts;
- milestone history and release evidence;
- local setup, testing, demo, and recovery procedures;
- security and repository rules that future work must preserve;
- known limitations and the next development stages.

This is not a marketing summary. It is meant to let the owner, a professor, or a future developer recover the reasoning and continue the work without reconstructing it from commit history.

## 2. Project objective

The long-term project is an adaptive LLM router. A router receives a user request, applies hard requirements such as context length, and chooses a model according to preferences such as cost, quality, or latency.

The project deliberately begins with evidence collection instead of jumping directly to a learned router. A routing policy is only credible if the underlying model calls, scores, failures, latency, token use, cost, and model identity are observable and reproducible.

The milestone sequence therefore follows this logic:

1. **Checkpoint 1: evidence layer.** Compare two fixed models, preserve a versioned registry, demonstrate hard eligibility filtering, run a fixed benchmark, and store inspectable results.
2. **Checkpoint 2: transparent routing layer.** Add fixed baselines, an explainable rule policy, user priority controls, hard-requirement precedence, a second dated paid model pool with its own saved benchmark matrix, offline replay with a results dashboard, and visible policy acceptance matrices.
3. **Later work: broader and learned routing.** Expand the task matrix, create better quality and confidence estimates, compare stronger routing methods against the fixed and rule baselines, and only then consider learned or multi-objective routing.

The current application completes the first two layers. It does not claim that a small rule policy is the final adaptive router.

## 3. Source-of-truth hierarchy

When documents disagree, use this order:

1. The current code, schemas, tests, and committed benchmark artifacts.
2. This file and milestone documents in `docs/`.
3. The safer, narrower implementation decisions recorded in the original handover.
4. The broad proposal and presentation language.

The proposal describes the eventual research direction. It must not be used to imply that later-stage work such as learned routing, Jev integration, local inference, or large benchmark suites already exists.

## 4. Milestone status

### Checkpoint 1: complete

Checkpoint 1 established a reproducible comparison and benchmark system:

- one prompt can be sent concurrently to two pinned models through one project-owned adapter interface;
- each result preserves its own response, status, latency, token usage, cost when available, requested model, and served model;
- a frozen model registry records context length, pricing, modalities, supported parameters, and capabilities;
- a deterministic hard filter excludes models below a requested context length;
- a fixed 12-question GSM8K sample produces 24 logical model-question cells;
- every provider attempt and final cell can be persisted and summarized;
- interrupted benchmark work can resume without duplicating completed cells;
- sanitized benchmark evidence remains viewable offline;
- a React interface exposes comparison, eligibility, and benchmark views;
- backend, frontend, integration, build, and secret checks run in CI.

Checkpoint 1 release information:

- tag: `checkpoint-1`
- tagged commit: `be52231a98dabc8cd4fa687457951267e9842fcf`
- release: `https://github.com/mian-abd/Snr/releases/tag/checkpoint-1`

### Checkpoint 2: complete

Checkpoint 2 adds the routing layer required by the proposal schedule through the week of October 15 and the October 22 checkpoint. The proposal's three Checkpoint 2 commitments map to the application as follows:

| Proposal commitment (Oct 22) | Delivered as |
| --- | --- |
| Two fixed-model baselines and a simple rule-based router on the same benchmark data, compared on accuracy, response time, and cost | Six strategies replayed over the same saved matrix for each pool, with accuracy, median/p95 latency, total cost, and cost per correct answer |
| Same prompt routed differently under at least two priorities | Four priorities plus a hard minimum-context requirement, local preview, and acceptance matrices |
| Basic results dashboard showing the selected model and summary results | Results dashboard plus a per-prompt table showing the selected model, reason, and outcome for every question |

Implemented:

- fixed model baselines;
- four visible priorities: balanced, lower cost, higher quality, and faster response;
- hard requirements evaluated before preferences;
- an inspectable rule-based policy with visible task signals and explanation text;
- two pools: the preserved Checkpoint 1 free pool (`rule_based_v1`) and a dated three-model paid pool (`rule_based_paid_v1`);
- a 36-cell paid GSM8K matrix on the identical Checkpoint 1 protocol, collected behind a cost estimate and a $1 cap;
- local decision preview with no key and no provider call;
- a one-model live route path that never calls an unselected fallback, verified live on all three paid models;
- offline strategy replay over either saved matrix, with per-prompt decisions;
- deterministic acceptance matrices (5 free-pool cases, 7 paid-pool cases);
- a rebuilt 9-slide Checkpoint 2 deck, full speaking script, live demo guide, progress record, and backup demo recording.

The proposal's next items (train/validation/test split, feature extraction, learned router) belong to the week of October 22 onward and Checkpoint 3. They were deliberately not started.

## 5. Current system architecture

```text
Browser
  React + TypeScript + TanStack Query + Radix UI
  ├── Route
  │   ├── local decision preview
  │   ├── one-model live route
  │   ├── deterministic policy acceptance matrix
  │   └── offline strategy replay
  ├── Compare
  │   └── same prompt sent to both fixed models
  ├── Eligibility
  │   └── minimum-context hard filter
  └── Benchmark
      └── fixed GSM8K run, progress, summary, and records
          │
          ▼
FastAPI
  ├── versioned HTTP API
  ├── frozen model registry and live-catalog drift check
  ├── project-owned ModelAdapter protocol
  ├── LiteLLM OpenRouter adapter
  ├── explicit retry service
  ├── rule policy and validation cases
  ├── offline routing replay
  ├── benchmark runner and exact numeric scorer
  └── atomic JSON and append-only JSONL storage
          │
          ▼
OpenRouter
  ├── free pool (Checkpoint 1 evidence)
  │   ├── google/gemma-4-26b-a4b-it:free
  │   └── nvidia/nemotron-3-ultra-550b-a55b:free
  └── paid pool (Checkpoint 2 evidence)
      ├── google/gemma-4-26b-a4b-it
      ├── inception/mercury-3
      └── google/gemini-4-argon
```

The production demo builds the React bundle and serves it from FastAPI, so the complete application uses one local URL: `http://127.0.0.1:8000`.

## 6. Repository layout

```text
backend/
  app/
    api/              FastAPI route handlers
    benchmarks/       GSM8K loading, scoring, running, aggregation
    domain/           Pydantic request, result, and persistence contracts
    providers/        Adapter protocol, LiteLLM adapter, retry service
    registry/         Snapshot loading, drift checks, eligibility filtering
    routing/          Rule policy, validation matrix, offline replay
    storage/          Atomic JSON, JSONL, and sanitization
    config.py         Server settings and secret loading
    main.py           Application construction and static serving
    state.py          Service construction and benchmark coordinator
  tests/              Backend unit and integration tests
  pyproject.toml      Python package and tool configuration
  uv.lock             Locked Python dependency graph

frontend/
  src/
    api/              Typed client, project types, generated OpenAPI types
    components/       Shared UI components
    features/         Route, Compare, Eligibility, Benchmark panels
    styles/           Design tokens and global styling
  e2e/                Playwright smoke flows
  openapi.json        Generated FastAPI contract
  package-lock.json   Locked Node dependency graph

data/
  benchmarks/         Fixed GSM8K sample and provenance metadata
  registry/           Frozen free (2026-09-30) and paid (2026-10-22) OpenRouter snapshots
  demo/checkpoint-1/  Committed sanitized 24-cell free-pool benchmark evidence
  demo/checkpoint-2-paid/  Committed sanitized 36-cell paid-pool benchmark evidence
  local/              Ignored local runs, request budgets, and opt-in manual comparisons

docs/
  checkpoint-1.md
  checkpoint-2.md
  research-basis.md
  build-handover.md
  progress-through-oct-15.md
  presentation-script.md
  live-demo-guide.md
  demo-script.md
  presentations/      Final checkpoint deck
  demo/               Backup checkpoint recording

scripts/
  bootstrap.ps1       Install locked Python and Node dependencies
  dev.ps1             Start separate development servers
  demo.ps1            Build and serve the one-URL production demo
  check.ps1           Run backend and frontend verification
  generate-api-types.ps1
```

## 7. Runtime and dependency decisions

### Backend

- Python `3.12` only, managed by `uv`.
- FastAPI provides the local versioned API and OpenAPI schema.
- Pydantic validates every external and stored contract.
- LiteLLM is used as a Python SDK wrapper for OpenRouter, not as a proxy.
- `httpx` is used for HTTP and test integration.
- `filelock` prevents concurrent modification of one benchmark run.
- Ruff, mypy strict mode, pytest, pytest-asyncio, and respx provide verification.

LiteLLM Router, automatic fallbacks, caching, callbacks, and its proxy server are intentionally not used. Routing behavior belongs to this repository and must remain visible.

### Frontend

- React 19 and TypeScript.
- Vite for development and production bundling.
- TanStack Query for server state and benchmark polling.
- Radix primitives for accessible interactions.
- CSS Modules and project-owned tokens for styling.
- Lucide icons used only when they improve scanability.
- Vitest and Testing Library for component behavior.
- Playwright for production-style smoke flows.

### Why OpenRouter

OpenRouter provides one API and one catalog for models from different providers. This lets the project focus on comparison, evaluation, and routing rather than maintaining separate provider clients. The exact OpenRouter model slugs are still pinned so that a hidden upstream router cannot invalidate the baseline.

## 8. Fixed model registry

The committed snapshot is `data/registry/openrouter-2026-09-30.json`.

Tracked model identities:

1. `google/gemma-4-26b-a4b-it:free`
   - display name: Google Gemma 4 26B A4B
   - snapshot context length: 262,144 tokens
   - role in the current policy: cheaper/smaller baseline
2. `nvidia/nemotron-3-ultra-550b-a55b:free`
   - display name: NVIDIA Nemotron 3 Ultra 550B A55B
   - snapshot context length: 1,000,000 tokens
   - role in the current policy: stronger baseline

The registry is immutable at normal runtime. A real comparison, route, or benchmark first checks the live OpenRouter catalog. The check confirms that both exact slugs still exist, still expose a free route, still support text output, and still match the tracked metadata. Drift fails closed before generation. The application never silently replaces a missing model.

### Paid routing pool (Checkpoint 2)

The second snapshot is `data/registry/openrouter-paid-2026-10-22.json` (snapshot ID `openrouter-paid-2026-10-22-cp2`, models checksum `3e721e74b00de139a8629b131c92c7e6a48fd61d443bb1632e522194825d6a06`). It is loaded with `expected_model_ids=PAID_MODEL_IDS` and `require_free=False` (`backend/app/state.py`). Models are stored in ascending price order, which the policy relies on for hard-requirement fallbacks.

| Model | Context | Prompt $/token | Completion $/token | Policy role |
| --- | ---: | ---: | ---: | --- |
| `google/gemma-4-26b-a4b-it` | 262,144 | 0.0000000765 | 0.000000255 | lowest cost |
| `inception/mercury-3` | 1,000,000 | 0.0000001 | 0.00000035 | low latency / balanced mid tier |
| `google/gemini-4-argon` | 1,048,576 | 0.000002 | 0.00001 | higher quality |

All three IDs, prices, and context lengths were confirmed against the live public catalog (`https://openrouter.ai/api/v1/models`, 468 models listed) on 2026-10-22 before any paid call. For the paid pool the live preflight checks prices for equality with the snapshot instead of requiring zero. Prices are compared as `Decimal` values: a string comparison would always report drift because `str(Decimal("0.0000000765"))` renders as `7.65E-8` while the catalog returns `0.0000000765`.

The free pool remains the immutable Checkpoint 1 evidence pool. The paid pool is a separately versioned addition; nothing in Checkpoint 1 was rewritten.

Second paid snapshot (live calls since 2026-10-23): `data/registry/openrouter-paid-2026-10-23.json` (snapshot ID `openrouter-paid-2026-10-23-cp2`, checksum `fdce62a53c58000505335fa3e82ae60c1fceadc1d8c55912916bb6e6d5df2bd7`). On 2026-10-23 the live preflight refused every paid call because OpenRouter had raised `google/gemma-4-26b-a4b-it` to $0.00000009 per prompt token and $0.0000003 per completion token. The new snapshot differs from 10-22 only in those two prices (`test_paid_snapshots_differ_only_in_dated_gemma_price`). `PAID_REGISTRY_PATH` points at it. The 10-22 snapshot is kept because the committed 36-cell matrix and its manifest were collected on it; the paid runner's "latest run" view therefore falls back to that committed evidence. Gemma remains the cheapest paid model, so the registry's ascending price order and every routing role are unchanged. Future price changes should get a new dated snapshot the same way, never an in-place edit.

## 9. Backend contracts

### Generation request

`GenerationRequest` contains:

- UUID request ID;
- exact model ID;
- prompt and optional system prompt;
- temperature;
- maximum output tokens;
- timeout;
- optional run and sample identifiers.

### Generation result

`GenerationResult` normalizes:

- requested and served model identity;
- provider;
- status: success, provider error, timeout, rate limit, invalid response, or model mismatch;
- response text;
- prompt, completion, and total tokens;
- end-to-end latency;
- cost and cost source;
- error code and sanitized message;
- start and completion timestamps;
- explicit attempt number.

Provider request IDs exist only where needed for local raw evidence. Public API responses and sanitized artifacts remove them.

### Routing decision

`RoutingDecision` records:

- strategy ID;
- requested priority;
- minimum context requirement;
- selected model;
- eligible models after hard filtering;
- detected task signals;
- a human-readable reason.

### Validation report

`RoutingValidationReport` records the policy version, registry snapshot, overall result, passed count, and full reference cases. Each case preserves the input prompt, priority, requirement, expected model, actual decision, and pass/fail value.

## 10. HTTP API

All application routes use the `/api/v1` prefix.

| Method and route | Purpose | Provider call |
| --- | --- | --- |
| `GET /health` | Server, registry, credential-configured, and benchmark state | No |
| `GET /models?pool=` | Frozen registry and snapshot metadata for one pool (default free) | No |
| `POST /eligibility` | Deterministic minimum-context filtering across both pools, or one pool with `pool` | No |
| `POST /comparisons` | Send the same prompt concurrently to every model in the chosen pool | Yes |
| `GET /benchmarks/gsm8k/estimate?pool=&mode=` | Worst-case cost, cells, cap, and whether confirmation is required | No |
| `GET /routing/models` | Paid-pool registry snapshot | No |
| `POST /routing/decisions` | Preview one routing decision (`pool`: `baseline` or `paid`) | No |
| `GET /routing/validation?pool=` | Run the pool's deterministic acceptance cases (5 free, 7 paid) | No |
| `GET /routing/dashboard?pool=` | Replay six strategies over the pool's saved matrix, with per-prompt decisions | No |
| `POST /routes` | Select one model in the chosen pool and send exactly one live generation request | Yes |
| `POST /benchmarks/gsm8k/runs` | Start or resume a pilot/full run for a pool; paid runs need `confirmed_estimate_usd` equal to the current estimate and within the cap | Yes |
| `GET /benchmarks/runs/latest?pool=` | Load the pool's latest local or committed run | No |
| `GET /benchmarks/runs/{run_id}` | Load manifest and aggregate summary | No |
| `GET /benchmarks/runs/{run_id}/records` | Load paginated result records | No |

The frontend types are regenerated from FastAPI OpenAPI and CI rejects schema drift.

## 11. Checkpoint 1 benchmark protocol

### Dataset

- dataset: `openai/gsm8k`
- configuration: `main`
- split: `test`
- revision: `b0bb162abedc65e1fdd8e93ed090fd7598ee68bc`
- selection seed: `498`
- source indices: `30, 263, 507, 509, 539, 756, 780, 851, 987, 1218, 1227, 1251`
- sample size: 12
- committed source checksum: `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14`

### Generation protocol

- temperature: `0`
- maximum output tokens: `512`
- streaming: disabled
- one response per attempt
- one in-flight benchmark request at a time
- alternating model order by question
- at most two attempts per logical cell
- retry only timeouts, network failures, HTTP 408, HTTP 429, and HTTP 5xx
- no hidden fallback model

The benchmark prompt requires concise reasoning and a final line formatted as `FINAL_ANSWER: <number>`.

### Scoring

The expected answer comes from GSM8K's canonical `####` suffix. Candidate extraction tries:

1. `FINAL_ANSWER: <number>`;
2. a boxed numeric answer;
3. the last standalone numeric expression.

Normalization removes commas, currency symbols, and surrounding whitespace. Decimal comparison avoids binary floating-point errors. The metric is exact numeric match. An unparseable or truncated answer receives zero with an explicit extraction status. No LLM judge is used.

### Persistence

Every local run contains:

- `manifest.json` for protocol, status, hashes, Git commit, and progress;
- `attempts.jsonl` for each provider attempt as it completes;
- `results.jsonl` for one canonical result per logical cell;
- `summary.json` for aggregate counts, accuracy, latency, token use, cost, and errors.

Attempts are append-only and flushed immediately. Manifest and summary files use temporary-file replacement. Resume identity combines dataset revision, sample ID, model ID, and generation-configuration hash.

## 12. Committed benchmark evidence

Committed run: `gsm8k-full-20261001T134908Z-0b94a2ed`.

The run completed all 24 logical cells. Fifteen provider calls succeeded and nine ended in recorded Gemma rate-limit failures.

| Model | Cells | Successful | Exact matches | Failed | Accuracy over all cells | Mean successful latency | Tokens | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemma | 12 | 3 | 3 | 9 | 25.0% | 5,646.55 ms | 1,058 | $0 |
| Nemotron | 12 | 12 | 8 | 0 | 66.7% | 19,858.77 ms | 6,115 | $0 |

Interpretation rules:

- the nine Gemma rate limits are availability failures, not math answers;
- accuracy over all cells intentionally keeps failures in the denominator;
- the 12-question sample demonstrates the pipeline but does not establish a statistically significant ranking;
- free-tier latency and availability can change with shared provider capacity;
- later evaluations must distinguish answer quality from served-request availability.

## 12a. Checkpoint 2 paid benchmark evidence

Committed run: `gsm8k-paid-full-20261023T044929Z-5f90eace` in `data/demo/checkpoint-2-paid/` (manifest, sanitized `results.jsonl`, summary). A preceding 6-cell pilot, `gsm8k-paid-pilot-20261023T044859Z-e4857827`, stays in ignored `data/local/runs/`; it went 6/6 served and 6/6 correct for under half a cent and confirmed that the reasoning-capable models were not truncated by the fixed 512-token limit.

Protocol is identical to Checkpoint 1: same 12 GSM8K questions (seed 498, same source indices and checksum), prompt template `gsm8k-cp1-v1`, system prompt, temperature 0, 512 max tokens, 90 s timeout, at most two attempts per cell, alternating model order, exact numeric scoring. Only the registry changes, so the generation-config hash is the same as Checkpoint 1.

Collection command (prints the estimate; spends nothing without `--confirm`):

```powershell
uv run --project backend python -m app.benchmarks.paid_matrix --mode pilot
uv run --project backend python -m app.benchmarks.paid_matrix --mode full --confirm
```

`backend/app/benchmarks/paid_matrix.py` estimates worst-case cost as (prompt characters / 4 + 16) prompt tokens plus the full 512 completion tokens, at registry prices, times two attempts. It refuses to run above `SPEND_CAP_USD = 1.00`. Its request budget is separate from the free benchmark (`data/local/paid-provider-request-budget.json`, 100 per day). After a complete full run it sanitizes the run into `data/demo/checkpoint-2-paid/`.

Estimate: $0.0227 for the pilot, $0.1373 for the full run. Actual provider-reported spend for the full run: about $0.0228.

| Model | Cells | Served | Correct | Median latency | Tokens cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemini 4 Argon | 12 | 12 | 12 | 4,991.7 ms | $0.020892 |
| Gemma 4 26B | 12 | 12 | 11 | 2,940.7 ms | $0.001035 |
| Mercury 3 | 12 | 10 | 10 | 579.4 ms | $0.000900 |

Failures and misses:

- GSM8K #1227 and #1251, Mercury 3: `invalid_response` / `empty_content` ("Provider returned empty text content"). Kept in the denominator.
- GSM8K #1227, Gemma 4 26B: served, extracted 5, expected 66.

`BenchmarkRunner` gained `demo_name`, `run_prefix`, and `budget_file` arguments, and `latest_run()` now only returns runs whose manifest uses the runner's own registry snapshot, so the free-pool Benchmark tab never shows a paid run.

## 13. Checkpoint 2 routing policy

The policy ID is `rule_based_v1`.

### Hard requirements first

The minimum-context filter evaluates every model before any preference. A model becomes ineligible if it is disabled or its context length is below the requirement.

The required demonstration uses 500,000 tokens:

- Gemma: excluded because `262144 < 500000`;
- Nemotron: eligible because `1000000 >= 500000`.

If no model remains, routing returns a validation error. If only one model remains, a soft preference cannot override the hard requirement.

### Priorities

- **Lower cost:** select the designated cheaper/smaller baseline when eligible.
- **Higher quality:** select the designated stronger baseline when eligible.
- **Faster response:** select the smaller baseline for the first transparent latency baseline.
- **Balanced:** inspect simple prompt signals. Math, code, long prompts, or prompts containing several numbers select the stronger baseline. General prompts select the smaller baseline.

### Prompt signals

The policy exposes, rather than hides, its current features:

- `math` for calculation words, equation terms, or common arithmetic symbols;
- `code` for fenced code or common programming terms;
- `long_prompt` at 45 or more whitespace-separated words;
- `many_numbers` for at least four numeric values;
- `general` when none of the above appears.

These signals are intentionally simple. They establish an explainable baseline for later comparison; they are not a learned quality predictor.

### Paid pool policy (`rule_based_paid_v1`)

Same function, same signals, different designated roles (`backend/app/routing/policy.py`):

- **Lower cost:** `PAID_BUDGET_MODEL_ID` = `google/gemma-4-26b-a4b-it`.
- **Higher quality:** `PAID_QUALITY_MODEL_ID` = `google/gemini-4-argon`.
- **Faster response:** `PAID_EFFICIENT_MODEL_ID` = `inception/mercury-3`.
- **Balanced:** `effort_score(signals)` counts the higher-effort signals in `HIGH_EFFORT_SIGNALS` = {math, code, long_prompt, many_numbers}. Score 0 → budget model; 1 or 2 → efficient model; `HIGH_EFFORT_THRESHOLD` = 3 or more → quality model.

The free pool's balanced rule is unchanged: any higher-effort signal selects Nemotron.

When a designated model is filtered out, the cost and latency roles fall back to the first eligible model and the quality role to the last eligible model in registry order. Because both registries are price-ordered, a cost preference at 500,000 tokens in the paid pool falls to Mercury 3.

Why the three-signal tier: every GSM8K prompt carries the `math` signal (the template begins with "Solve"), so a one-signal escalation would send every benchmark prompt to the quality model and make balanced identical to the fixed strong baseline. On the 12 benchmark prompts the signal counts are: 1 signal for #851; 2 for #30, #263, #507, #509, #539, #756; 3 for #780, #987, #1218, #1227, #1251. The threshold was written after seeing these input signal counts and the 6-cell pilot, but before the full paid matrix outcomes existed, and it was not changed afterward. This is disclosed on slide 7 and in `docs/checkpoint-2.md`.

### Decision preview and live route

Decision preview runs only against the committed registry. It needs no API key and makes no network request. It exists so the policy can be demonstrated even when free provider capacity is unavailable.

The live route performs the same decision, validates the current catalog, and calls only the selected model. There is no silent fallback. Provider failures remain visible.

## 14. Five-case policy acceptance matrix

The Route view and `GET /api/v1/routing/validation` execute these fixed local cases:

| Case | Priority | Minimum context | Expected model | Behavior tested |
| --- | --- | ---: | --- | --- |
| Cost preference | Cost | 1 | Gemma | Soft cost preference |
| Latency preference | Latency | 1 | Gemma | Initial latency baseline |
| Quality preference | Quality | 1 | Nemotron | Stronger-model preference |
| Balanced complex task | Balanced | 1 | Nemotron | Visible math signal |
| Hard requirement override | Cost | 500,000 | Nemotron | Eligibility overrides cost |

The UI shows expected and actual selections, the policy explanation, and an overall pass count. These are deterministic acceptance checks, not a provider benchmark.

Paid-pool cases (`GET /api/v1/routing/validation?pool=paid`, strategy `rule_based_paid_v1`):

| Case | Priority | Minimum context | Expected model | Behavior tested |
| --- | --- | ---: | --- | --- |
| `cost_general` | Cost | 1 | Gemma 4 26B | Lowest-price role |
| `latency_general` | Latency | 1 | Mercury 3 | Low-latency role |
| `quality_general` | Quality | 1 | Gemini 4 Argon | Quality role |
| `balanced_general` | Balanced | 1 | Gemma 4 26B | 0 signals |
| `balanced_simple_math` | Balanced | 1 | Mercury 3 | 1 signal ("Calculate 18 + 24.") |
| `balanced_complex_math` | Balanced | 1 | Gemini 4 Argon | 3 signals (math, many_numbers, long_prompt) |
| `hard_requirement_override` | Cost | 500,000 | Mercury 3 | Gemma excluded before the cost preference |

## 15. Offline strategy replay

`GET /api/v1/routing/dashboard?pool=baseline|paid` reads the pool's committed `results.jsonl` (`EVIDENCE_DIRS` in `backend/app/routing/replay.py`: `checkpoint-1` or `checkpoint-2-paid`). It groups the model results for each sample and applies a strategy by selecting one existing record. It makes no model requests. A missing matrix returns 404.

Replayed strategies:

1. fixed cheaper/smaller model;
2. fixed stronger model;
3. rule router with cost priority;
4. rule router with quality priority;
5. rule router with latency priority;
6. rule router with balanced priority.

For each strategy, the API (`RoutingStrategySummary`) reports:

- selected-model counts;
- attempted, successful, and failed cells;
- exact-match accuracy over all selected cells;
- accuracy when served;
- mean, median, and p95 successful latency (p95 is nearest rank: `sorted[ceil(0.95 n) - 1]`, which for 12 prompts is the slowest served call);
- known total cost and cost per correct answer.

The dashboard also returns `prompts`: for each sample, the question text, detected signals, every saved model outcome (`ReplayCell`: status, correct, latency, cost), and every strategy's selection with its reason (`ReplaySelection`). The UI's per-prompt table uses this to show, for a chosen strategy, which model was picked for each question, why, and what happened.

Paid-pool replay results:

| Strategy | Selected | Correct | Median | p95 | Total cost | Cost / correct |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `fixed_cheap` | Gemma × 12 | 11/12 | 2,941 ms | 17,992 ms | $0.001035 | $0.000094 |
| `fixed_strong` | Gemini × 12 | 12/12 | 4,992 ms | 8,772 ms | $0.020892 | $0.001741 |
| `rule_cost` | Gemma × 12 | 11/12 | 2,941 ms | 17,992 ms | $0.001035 | $0.000094 |
| `rule_quality` | Gemini × 12 | 12/12 | 4,992 ms | 8,772 ms | $0.020892 | $0.001741 |
| `rule_latency` | Mercury × 12 | 10/12 | 579 ms | 1,098 ms | $0.000900 | $0.000090 |
| `rule_balanced` | Mercury × 7, Gemini × 5 | 12/12 | 823 ms | 8,772 ms | $0.011556 | $0.000963 |

Balanced matched always-Gemini accuracy at about 55% of its cost (−45%) and a roughly 6× faster median (4,992 / 823). Mercury's two empty responses were on #1227 and #1251, both three-signal prompts that balanced routes to Gemini, so they did not count against the balanced strategy. That is favorable alignment on a tiny sample, not evidence that the threshold generalizes.

Because every strategy selects from the same saved matrix, comparisons are controlled and reproducible. The replay is a retrospective estimate over twelve GSM8K prompts, not a live randomized trial.

## 16. Frontend behavior

### Persistent header

The header shows project name, checkpoint label, backend state, key-configured state, and both registry snapshot IDs (free and paid). It never displays the key.

### Route

- model pool selector: Checkpoint 2 paid pool (default) or Checkpoint 1 free pool; switching resets the current decision and reloads the pool's acceptance matrix and dashboard;
- candidate chips showing each pool model and its context length;
- editable prompt;
- four priority choices with pool-specific descriptions;
- numeric minimum-context requirement;
- one-click 500,000-token demonstration;
- provider-free preview;
- one-model live route when a key is configured;
- selected-model explanation and task signals;
- response, latency, tokens, cost, and status for a live route;
- pool acceptance matrix (5 or 7 cases);
- results dashboard: strategy table with accuracy, served cells, median and p95 latency, total cost, and cost per correct answer;
- per-prompt routing decisions with a strategy selector, the selected model and reason, outcome, latency, cost, and every saved model's outcome for that question.

### Compare

- pool switch (paid by default); one prompt sent concurrently to every model in the selected pool (2 free or 3 paid calls);
- independent result cards, so one failure does not hide the others; three columns for the paid pool;
- response, latency, tokens, cost, requested model, served model, and normalized error state;
- manual-save control off by default.

### Eligibility

- all five registry entries from both pools (four distinct models), with a pool column, context, modalities, capabilities, and per-million input and output prices;
- minimum-context input evaluated across both pools;
- explicit eligible/excluded result and reason;
- 500,000-token demonstration: both Gemma entries excluded; Nemotron, Mercury 3, and Gemini 4 Argon eligible.

### Benchmark

- pool switch (paid by default) with a pool-aware protocol summary (models and cells);
- pilot, full-run, and resume controls; a free run asks for a browser confirmation; a paid run first shows an inline box with the worst-case estimate, cell count, and $1 cap and starts only on **Confirm and start**;
- progress polling;
- saved summary metrics;
- expandable per-question evidence;
- automatic loading of the pool's committed evidence when no newer local run exists.

### Visual system

The interface uses a dark, data-dense console style inspired by OpenRouter's structure without copying its brand assets. It uses thin borders, restrained status colors, Inter for interface text, JetBrains Mono for identifiers and metrics, responsive stacking, visible focus states, reduced-motion support, and explicit loading, empty, error, partial-success, and completed states.

## 17. Reliability and failure handling

The project treats failure as evidence:

- manual comparisons return both per-model outcomes even when one fails;
- the benchmark continues after one permanent cell failure;
- only retryable categories receive a second attempt;
- model mismatch is a distinct final status and never receives a score;
- missing token or cost data stays null instead of being invented;
- provider-reported cost takes precedence, then registry calculation, then unavailable;
- catalog drift stops live work before generation;
- a process lock rejects a second benchmark writer;
- interrupted manifests can resume missing or retryable cells;
- error messages are sanitized before public storage or display.

Free provider rate limits cannot be increased by this application. Dedicated capacity requires an OpenRouter/provider account integration or a paid route. The application instead makes capacity failures understandable and keeps the provider-free policy and saved-evidence demonstrations available.

## 18. Security rules

These rules are mandatory for future work:

1. Store `OPENROUTER_API_KEY` only in ignored `backend/.env` or a secure environment variable.
2. Never place the key in React code, browser storage, URL parameters, documentation, test fixtures, commits, screenshots, or recorded terminal output.
3. Never return authorization headers or provider request IDs through public API responses.
4. Keep manual comparison saving opt-in and off by default.
5. Keep local runs under ignored `data/local/` unless a deliberate sanitization/export step creates a public artifact.
6. Run secret scanning before a release.
7. Preserve exact model identity checks and fail closed on drift.
8. Do not convert a provider failure into another model without an explicit, documented future policy.
9. Paid benchmark runs must print a cost estimate first, respect `SPEND_CAP_USD`, and require explicit confirmation.

Credential note (2026-10-22): the paid OpenRouter key now in ignored `backend/.env` was shared in plain text during development. It was never written to tracked files, logs, screenshots, the deck, or commits (verified by a staged-diff scan before each commit), but it should be rotated in the OpenRouter dashboard after the checkpoint and the new key placed only in `backend/.env`.

## 19. Testing strategy

### Backend coverage

- registry parsing and checksum validation;
- missing, malformed, and duplicate models;
- context-filter boundaries and explanations;
- provider normalization with complete or missing usage/cost;
- cost precedence;
- timeout, rate limit, provider failure, invalid response, and model mismatch;
- retryable versus permanent failures;
- numeric answer extraction and exact matching;
- manifest transitions, atomic writes, resume keys, and sanitization;
- routing priorities and task signals;
- hard-requirement precedence;
- five-case validation report;
- offline replay metrics;
- API behavior without a credential;
- partial comparison success and opt-in saving.

### Frontend coverage

- project and checkpoint status;
- live actions disabled when a key is absent;
- local route preview remains available;
- priority changes produce a visible preview;
- five-case policy result appears;
- saved replay remains available;
- comparison, eligibility, benchmark, and responsive states;
- production smoke flows through Playwright.

### Continuous integration

`.github/workflows/checkpoint.yml` runs on pushes and pull requests:

- locked Python sync;
- Ruff;
- mypy strict mode;
- pytest;
- OpenAPI regeneration and drift check;
- locked npm install;
- ESLint;
- Vitest;
- production frontend build;
- generated TypeScript schema drift check;
- Gitleaks across repository history.

Local verification command:

```powershell
./scripts/check.ps1
```

End-to-end smoke command:

```powershell
Push-Location frontend
npm run test:e2e
Pop-Location
```

## 20. Local setup and operating procedures

### First setup

```powershell
Copy-Item .env.example backend/.env
# Put the replacement API key only in backend/.env.
./scripts/bootstrap.ps1
```

### Development mode

```powershell
./scripts/dev.ps1
```

The frontend development server uses `http://localhost:5173`; FastAPI runs separately.

### Production-style demo

```powershell
./scripts/demo.ps1
```

The script builds the frontend and serves the complete application at `http://127.0.0.1:8000`.

### Demo order designed to survive provider limits

1. Open Route with the paid pool and show the 7/7 acceptance matrix.
2. Preview Lower cost (Gemma) and Higher quality (Gemini Argon) on the same prompt.
3. Set the minimum context to 500,000 with Lower cost and show the preference overridden to Mercury.
4. Set context back to 1 and make one live routed call.
5. Walk the results dashboard and the per-prompt balanced decisions.
6. Optionally switch to the free pool to show the original 24-cell evidence, Eligibility, and Benchmark records.

Only step 4 needs the provider. Full detail is in `docs/live-demo-guide.md`.

### Local runtime notes (Windows, this machine)

- Some sandboxed (MSIX-packaged) terminals on this machine virtualize `%APPDATA%` writes under `%LOCALAPPDATA%\Packages\...\LocalCache\Roaming`. On 2026-10-22 the uv-managed CPython 3.12.14 that `backend/.venv` points to was missing from that view; `uv python install 3.12.14` followed by `uv sync --project backend --extra dev --locked` repaired it. Always pass `--extra dev`, otherwise `uv sync` uninstalls pytest, ruff, and mypy.
- Set `UV_CACHE_DIR` to `tmp/uv-cache` inside the repository if the default uv cache is not writable.
- Without the script, the demo server is `backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000` after `npm run build` in `frontend/`.
- Playwright video recording needs `npx playwright install ffmpeg` once.

## 21. Presentation and deliverables

Checkpoint 2 presentation assets:

- `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx` (9 slides, 20 × 11.25 in, Roboto, speaker notes on every slide)
- `docs/presentation-script.md` (full talk track plus likely questions)
- `docs/live-demo-guide.md`
- `docs/demo-script.md`
- `docs/demo/checkpoint-2-backup-demo.webm` (re-recorded 2026-10-22 against the paid-pool UI)
- `docs/progress-through-oct-15.md`

Deck history and format. The original Checkpoint 2 deck (8 slides, 20 × 11.25 in) was built from image-filled freeform shapes: every background and card was a picture, and those pictures still contained text from an older draft. In real PowerPoint the new text sat over that ghost text, and several titles wrapped mid-word ("Toda / y", "NEMOTRO / N", "CHALLENG / E"). On 2026-10-22 it was first replaced by a 13.33-inch deck in the app's style. On 2026-10-23 the owner asked for the original format, so the deck was rebuilt again in that format with native shapes: the same canvas, Roboto (an Office cloud font, also embedded in the original), lime `C1FF72` / `94DD26` / `7ED957` on near-black, white titles with the short lime underline, numbered cards with lime bracket connectors, the chip title image (the original's transparent chip layer), and a cleanly cropped and faded copy of the stair photo for the closing slide. A results-dashboard slide was added in the same style because the dashboard is a Checkpoint 2 commitment and the original deck had no slide for it.

The deck is generated by `tmp/presentation-build/build_checkpoint2_deck_format.cjs` (ignored; its images are in `tmp/presentation-build/format-assets/`, and `capture_format_screen.cjs` captures the Route screenshot) and checked slide by slide by exporting PNGs through the installed PowerPoint. The backup recording is made by `record_backup_demo.cjs`.

Slides:

1. Title (chip image).
2. Today: what changed, rule-based routing, benchmark evidence + dashboard, priority + requirement tests, then live demo.
3. Evidence → decision: prompt, filters, rule, model; hard requirements first, one model plus a reason.
4. Rule routing · three roles: request fanning out to Gemma, Mercury, and Gemini with context, role, GSM8K, median, and price.
5. CP2 • Benchmark evidence: per-model correct, served, median, and cost on the 36-cell paid matrix; CP1 free pool unchanged.
6. Results dashboard: six strategies, with the 12/12, −45% cost, and 6× median callouts and the caveats.
7. Policy tests • same prompt: Lower cost → Gemma, Higher quality → Gemini, cost + 500K → Mercury; 12/12 acceptance cases.
8. What shipped: live Route screenshot and the four delivered items (the live demo follows this slide).
9. What I learned: challenge, response, next step, questions.

The speaker should say clearly that Gemma's nine Checkpoint 1 failures were provider rate limits and Mercury's two Checkpoint 2 failures were empty provider responses, not incorrect math answers, and should present the 12-question sample as a functional checkpoint rather than a conclusive leaderboard.

## 22. Build and release history

Important commits currently in `main`:

- `680c20d` sanitized provider error metadata;
- `aedbee1` added Checkpoint 1 benchmark evidence;
- `be52231` loaded committed benchmark evidence and became the `checkpoint-1` tag;
- `6d02cb9` added the Checkpoint 1 handover and presentation guide;
- `5cfe1e1` labeled benchmark provider failures accurately;
- `0619d1b` improved provider-failure presentation;
- `88615c0` prepared the demo for provider capacity limits;
- `3f47647` added transparent Checkpoint 2 routing;
- `d32c0ee` added provider-free routing decision preview;
- `4825477` packaged the first Checkpoint 2 deck, script, demo guide, progress record, and backup recording;
- `3797971` added the paid three-model pool, the 36-cell paid matrix, paid acceptance cases, the extended results dashboard, the decimal price-drift fix, and this document;
- `c9be064` rebuilt the deck, re-recorded the backup demo, and rewrote the Checkpoint 2 documents;
- `9dcbf82` rebuilt the deck in the owner's original Checkpoint 2 format and updated the speaking script;
- `1d920fd` put both pools on every tab and added the 2026-10-23 paid snapshot. It is tagged `checkpoint-2`; at the owner's request the tag was moved here from `9dcbf82` on 2026-10-23, force-updated in place so the release stayed attached. The GitHub release `https://github.com/mian-abd/Snr/releases/tag/checkpoint-2` (published 2026-10-23 by mian-abd, with `checkpoint-2-demo.webm` attached) follows the Checkpoint 1 release format, lists the all-tabs work and the 2026-10-23 snapshot, and links the passing CI run for `1d920fd` (`https://github.com/mian-abd/Snr/actions/runs/39990257462`). The attached video was recorded before the all-tabs change and shows the Route tab flow;
- the commit after `1d920fd` corrected this note on `main` only. The copy of this file inside the tagged commit still says the tag is on `9dcbf82`, and the owner chose to leave the tag where it is.

History rewrite (2026-10-23, approved by the owner): the original `13ccb23`, `9758beb`, and `bcda7cb` were rebuilt as `3797971`, `c9be064`, and `9dcbf82`. Two leaks were removed: a local temp-folder path in image alt text inside the deck committed in `9758beb`, and a tool-specific filename reference in that version of this file. Authors, dates, and messages were preserved and the final tree is byte-identical. `main` was force-pushed with a lease, and the `checkpoint-2` tag was force-updated in place so the release stayed attached. GitHub may keep serving the old commits by direct SHA until it garbage-collects them; removing them completely requires a GitHub Support request. Older versions of `docs/presentation-script.md` (Oct 1–19) still quote two third-party model names that an early Checkpoint 1 slide used as placeholders; those are model names, not attribution, and were left in history.

### Build log, 2026-10-22 evening session

1. Read the original proposal (Sept 17 draft 2) and confirmed the stopping point: the Checkpoint 2 commitments and the work-plan weeks through October 15. The week of October 22 items (data split, feature extraction, learned router) were not started.
2. Found the uv-managed Python missing from the sandboxed `%APPDATA%` view and repaired it (section 20).
3. Verified the three paid model IDs, prices, and context lengths against the live public catalog.
4. Fixed two defects left in the uncommitted paid-pool work: the paid registry's placeholder checksum, and the string-based price comparison that would have reported drift on every paid call.
5. Generalized `BenchmarkRunner` and added `app.benchmarks.paid_matrix` with the estimate, cap, and confirmation gate. Ran the 6-cell pilot, then the 36-cell full run.
6. Added `effort_score` and the paid balanced tiers, the seven paid acceptance cases, and pool-aware validation and dashboard endpoints.
7. Extended `RoutingStrategySummary` with median and p95 latency and cost per correct answer; added `ReplayCell`, `ReplaySelection`, and `ReplayPrompt` to the dashboard.
8. Rebuilt the Route panel: pool selector driving candidates, descriptions, acceptance matrix, and dashboard; extra dashboard columns; per-prompt decision table; model chips by name.
9. Made three live routed calls through `POST /api/v1/routes` on the paid pool: cost → Gemma (1,104 ms, $0.000019), latency → Mercury (633 ms, $0.000044), quality → Gemini Argon (4,714 ms, $0.000674), all served with provider-reported cost.
10. Verified `./scripts/check.ps1` (Ruff, mypy strict, 30 backend tests, ESLint, 2 Vitest tests, production build), the 2 Playwright smoke tests, desktop rendering, and no horizontal overflow at 390 px with real data. Scanned the staged diff for key patterns before each commit.
11. Committed and pushed only as Mian Abdullah with no co-author or tool attribution, then rebuilt the deck, re-recorded the backup demo, rewrote the docs, and tagged the release.

### Build log, 2026-10-23

1. Published the `checkpoint-2` GitHub release in the Checkpoint 1 format, with the backup demo attached.
2. Rebuilt the deck in the owner's original Checkpoint 2 format (section 21).
3. Rewrote history to remove the two leaks (section 22), re-verified, and repointed the release's CI link.
4. Re-read the proposal on model counts. It plans five base models (unnamed), a gateway with at least three models by Sept 24, a Model Registry view of every available model, and a Benchmark page that shows an estimated cost and requires confirmation. The owner chose: use the current four distinct models on every tab, allow paid runs from the Benchmark tab behind the estimate and confirmation, and give Compare a pool switch.
5. Backend: `AppServices` gained a paid `BenchmarkRunner` and coordinator plus `pool_*` helpers; `app/benchmarks/costs.py` holds the paid-run constants and estimate shared by the CLI and API; `/models`, `/comparisons`, `/eligibility`, `/benchmarks/runs/latest`, and `/benchmarks/gsm8k/runs` take a pool; a new `/benchmarks/gsm8k/estimate` endpoint returns the worst-case cost; paid starts require `confirmed_estimate_usd` to match the server's estimate and refuse estimates above the cap; only one benchmark of either pool can run at a time; health reports both snapshot IDs.
6. Frontend: shared `PoolSwitch`; Compare sends one prompt to every model in the selected pool with a three-column grid for the paid pool; Eligibility lists all five registry entries with a pool column and per-million prices; Benchmark has a pool switch and an inline confirmation box with the estimate and cap; the header shows both snapshots.
7. Live verification caught OpenRouter's overnight Gemma price increase ($0.0765 / $0.255 → $0.09 / $0.30 per million tokens): the drift check refused every paid call. With the owner's approval, added `openrouter-paid-2026-10-23.json` (only Gemma's prices changed; checksum `fdce62a53c58000505335fa3e82ae60c1fceadc1d8c55912916bb6e6d5df2bd7`) as the live paid registry and kept the 10-22 snapshot as the record of the saved matrix. Slide 4 now shows Gemma's $0.30 output price.
8. Verified 33 backend tests (including a test that the two paid snapshots differ only in Gemma's price), 3 Vitest tests (including the paid confirmation flow), 2 Playwright smoke tests, lint, types, and the build; a live paid comparison (Gemma 3,310 ms $0.000039, Mercury 747 ms $0.000073, Gemini Argon 6,681 ms $0.0018) and a live paid route (cost → Gemma, 819 ms, $0.0000115); every tab in the browser; and no horizontal overflow at 390 px. No paid benchmark run was started from the UI during verification.

## 23. Key decisions and rejected alternatives

### Use fixed model identities

Accepted: exact pinned slugs.  
Rejected for the benchmark: `openrouter/auto`, the free random router, or dynamic replacement.  
Reason: reproducible evidence requires knowing which model answered.

### Use LiteLLM only as an SDK

Accepted: `litellm.acompletion` behind a project-owned adapter.  
Rejected: LiteLLM proxy or LiteLLM Router.  
Reason: provider normalization is useful, but routing, retries, and observability must remain project behavior.

### Keep retry logic explicit

Accepted: zero LiteLLM retries plus a maximum of two project attempts.  
Rejected: invisible SDK retry loops.  
Reason: attempts and latency must be observable and persistable.

### Start with exact numeric scoring

Accepted: GSM8K and Decimal exact match.  
Rejected for the checkpoint: an LLM judge.  
Reason: the scoring rule should be deterministic and inexpensive.

### Replay before new expensive evaluation

Accepted: select results from the same saved model-by-prompt matrix.  
Rejected: rerun all strategies live during Checkpoint 2.  
Reason: replay controls the evidence, avoids new provider variability, and works offline.

### Separate hard constraints from preferences

Accepted: eligibility first, routing second.  
Rejected: a single weighted score that can trade away a required context length.  
Reason: hard requirements must remain inviolable and easy to explain.

### Keep the first router interpretable

Accepted: fixed baselines plus a small rule policy.  
Rejected for Checkpoint 2: prematurely training a model on twelve math prompts.  
Reason: the first router must be a meaningful baseline, and the current evidence is too small for a credible learned policy.

### Keep Jev for a later typed-decision experiment

Jev may help represent a future structured routing decision or confidence value. It does not generate the two natural-language model answers required by Checkpoint 1 and is not used as a comparison model.

## 24. Known limitations

- The evaluation contains twelve GSM8K questions and one task family, in two matrices (free 24 cells, paid 36 cells).
- The rule policy uses hand-written lexical signals; every GSM8K prompt carries the `math` signal because of the template.
- Cost, latency, and quality preferences map to designated model roles rather than calibrated predictions of success.
- The paid balanced tier threshold was chosen with knowledge of the benchmark prompts' signal counts (not their outcomes); there is no separate tuning set yet.
- Free model availability can be intermittent and can dominate observed accuracy over all cells.
- Paid prices and availability are a dated snapshot; live routing refuses to run on drift.
- The offline replay can compare choices available in the saved matrix but cannot estimate models absent from that matrix.
- There is no accuracy-vs-cost plot yet; comparison plots are a Checkpoint 3 deliverable.
- The in-process benchmark coordinator is appropriate for one local user, not distributed production work.
- There is no user authentication or multi-user data isolation.
- There is no database or cloud deployment.
- The current system does not train a learned router, estimate calibrated confidence, or optimize a Pareto frontier.
- The current benchmark is not a general statement about either model's overall quality.

These limitations are presentation requirements, not hidden defects. Future work should measure and address them rather than remove the disclosure.

## 25. Next development stages

### Stage 1: enlarge the evidence matrix

- Add more examples while preserving fixed revisions and checksums.
- Add at least one non-math task family so routing signals can be evaluated across domains.
- Add paid or dedicated-capacity routes if consistent availability is required.
- Preserve raw availability separately from correctness among served calls.
- Record repeated trials when provider nondeterminism or latency variance matters.

### Stage 2: improve policy features

- Replace simple prompt-length and keyword signals with measured task features.
- Add structured capability requirements such as tool use, modality, and structured output.
- Estimate prompt tokens before applying a context requirement.
- Add policy-versioned confidence and abstention behavior.
- Add an explicit rule for what happens when no model is eligible.

### Stage 3: learned routing

- Define train, validation, and held-out test partitions before fitting a policy.
- Train only after the matrix has enough task and model diversity.
- Compare learned routing against both fixed baselines and `rule_based_v1`.
- Optimize an explicit objective instead of saying “best model” without a definition.
- Calibrate confidence and test distribution shift.
- Keep model selection explanations and full evaluation records.

### Stage 4: broader evaluation and operations

- Consider EvalPlus, HumanEval, MMLU-Pro, or other suitable benchmarks only when their licenses, scoring, and computational cost fit the research question.
- Add Docker, local inference, or Ollama only if reproducible deployment or privacy becomes a defined requirement.
- Add a database and queued job worker only when concurrent or remote use justifies them.
- Add cloud deployment and authentication only after local research behavior is stable.

## 26. Rules for future contributors and agents

1. Read this document, `README.md`, `docs/checkpoint-2.md`, and relevant tests before changing routing behavior.
2. Do not change a model slug, dataset revision, sample, prompt template, or scorer without versioning the experiment.
3. Do not overwrite committed evidence with a new run under the same schema or benchmark version.
4. Keep provider calls behind the adapter and retry service.
5. Keep read-only policy preview and offline evidence usable without a credential.
6. Add or update Pydantic types before exposing new API behavior.
7. Regenerate `frontend/openapi.json` and `frontend/src/api/schema.d.ts` after backend contract changes.
8. Test hard-requirement boundaries and soft-priority behavior separately.
9. Preserve unrelated user work in a dirty worktree.
10. Never print or commit secrets.
11. Use the repository-local Git identity for Mian Abdullah and do not add bot or assistant attribution.
12. Push milestone documentation, code, generated schemas, and presentation materials together so they describe the same system.

## 27. Definition of Checkpoint 2 done

Checkpoint 2 is complete when all of the following remain true on `main`:

- the application starts through the one-command demo path;
- decision preview works without a provider call;
- cost, quality, latency, and balanced priorities produce deterministic choices in both pools;
- a 500,000-token hard requirement excludes Gemma before routing in both pools;
- the 5 free-pool and 7 paid-pool reference cases show expected-versus-actual passing results;
- a live route calls only the selected pinned model;
- the offline dashboard compares fixed and rule strategies over the same saved matrix for each pool (24 free cells, 36 paid cells), with per-prompt decisions;
- the raw benchmark evidence remains inspectable;
- API and UI contracts are synchronized;
- backend, frontend, build, end-to-end, and secret checks pass;
- the speaking script, deck, live demo guide, backup recording, and this context file match the actual application;
- the completed state is pushed to `main` and tagged `checkpoint-2`.

## 28. Quick recovery checklist

If work resumes on a new machine or after a long pause:

1. Clone `https://github.com/mian-abd/Snr`.
2. Check out `main` or the intended milestone tag.
3. Install Python 3.12, `uv`, Node 24, and npm.
4. Copy `.env.example` to `backend/.env` and add a valid key only if live calls are needed.
5. Run `./scripts/bootstrap.ps1`.
6. Run `./scripts/check.ps1`.
7. Run `./scripts/demo.ps1`.
8. Open `http://127.0.0.1:8000`.
9. Verify Route preview, the five-case matrix, the saved replay, Eligibility at 500,000, and the saved Benchmark before attempting a live call.
10. Review the latest commit, tags, and GitHub Actions result before making a new release.

