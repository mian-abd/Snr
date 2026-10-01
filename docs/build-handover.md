# Checkpoint 1 build handover

## What exists now

Adaptive LLM Router is a local web application that creates an auditable baseline for a later model-routing project. It does **not** choose a “best” model yet. Instead, it proves that the project can collect comparable evidence before automatic routing is added.

The released Checkpoint 1 application does four things:

1. It sends the same user prompt to two fixed OpenRouter model IDs through one shared adapter.
2. It shows each result independently, including text, latency, token use, cost when available, and a normalized failure state.
3. It filters the model registry before calling a model. At a 500,000-token requirement, Gemma is excluded and Nemotron stays eligible.
4. It runs and preserves a fixed 12-question GSM8K benchmark, producing 24 model-question records that can be inspected offline.

The public release is [checkpoint-1](https://github.com/mian-abd/Snr/releases/tag/checkpoint-1). Its tag points to commit `be52231a98dabc8cd4fa687457951267e9842fcf`.

## Current benchmark evidence

The committed demo artifact records run `gsm8k-full-20261001T134908Z-0b94a2ed`.

| Model | Logical cells | Successful calls | Exact matches | Provider failures | Reported cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| `google/gemma-4-26b-a4b-it:free` | 12 | 3 | 3 | 9 shared-pool rate limits | $0 |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 12 | 12 | 8 | 0 | $0 |

The nine Gemma failures are retained as rate-limit failures. They are not presented as incorrect math answers. The small sample demonstrates the experiment pipeline; it does not support a general ranking claim.

The evidence lives in `data/demo/checkpoint-1/`:

- `manifest.json` records the models, dataset revision, generation settings, Git commit, and completion state.
- `results.jsonl` contains one final result for each of the 24 cells.
- `summary.json` aggregates accuracy, latency, token use, cost, and failure counts.

The committed files exclude the API key, authorization data, provider request IDs, account identifiers, and machine-specific paths.

## Architecture in plain language

```text
React UI
  ├─ Compare: one prompt → two independent model calls
  ├─ Eligibility: registry metadata → include/exclude explanation
  └─ Benchmark: saved 24-cell evidence → summary and records
          │
          ▼
FastAPI API
  ├─ Registry loader and live catalog preflight
  ├─ LiteLLM/OpenRouter adapter
  ├─ GSM8K runner, scorer, retry policy, and request budget
  └─ JSON/JSONL storage and sanitization
          │
          ▼
OpenRouter and the two pinned models
```

### Backend

The Python backend lives in `backend/app/`.

- `providers/litellm_openrouter.py` defines the project-owned adapter around LiteLLM. It sends non-streaming requests, disables LiteLLM retries, times each call, normalizes failures, and checks that the returned model ID matches the requested model ID.
- `registry/` loads the committed OpenRouter snapshot and implements the pure minimum-context eligibility rule.
- `benchmarks/` loads the fixed GSM8K sample, renders the math prompt, extracts a numeric final answer, scores it with exact decimal matching, persists attempts, resumes safely, and creates summaries.
- `storage/` provides atomic JSON writes, append-only JSONL storage, and error-message sanitization.
- `api/routes.py` exposes the web API.

The public API routes are:

| Route | Purpose |
| --- | --- |
| `GET /api/v1/health` | Safe server health and credential-configured status |
| `GET /api/v1/models` | Frozen registry snapshot |
| `POST /api/v1/eligibility` | Minimum-context filtering result |
| `POST /api/v1/comparisons` | Concurrent two-model manual comparison |
| `POST /api/v1/benchmarks/gsm8k/runs` | Starts the fixed pilot or full benchmark |
| `GET /api/v1/benchmarks/runs/latest` | Latest local or committed saved run |
| `GET /api/v1/benchmarks/runs/{run_id}` | One run’s manifest and summary |
| `GET /api/v1/benchmarks/runs/{run_id}/records` | Paginated individual records |

### Frontend

The React application lives in `frontend/src/`. FastAPI serves its production build from one local URL.

- **Compare** has a prompt box, two fixed-model result cards, and an opt-in local-save switch.
- **Eligibility** has a compact registry table and a 500,000-token demonstration.
- **Benchmark** loads the committed run automatically, shows the locked protocol, aggregate metrics, and expandable individual results.

The design intentionally uses a dense, dark, OpenRouter-inspired console style. It uses no OpenRouter brand assets.

## Reproducibility rules

The benchmark cannot silently substitute models. Before a live comparison or run, it verifies that both exact model IDs still exist, remain free, support text output, and match tracked registry metadata. If metadata drifts, the application stops before generation.

Every benchmark request uses the same settings:

- System message: a careful grade-school math solver
- Temperature: `0`
- Maximum output tokens: `512`
- Streaming: off
- One in-flight benchmark request at a time
- Alternating model order by question
- At most two attempts for a logical cell, only for retryable failures

The fixed sample uses the official `openai/gsm8k` `main` test split, revision `b0bb162abedc65e1fdd8e93ed090fd7598ee68bc`, at source indices `30, 263, 507, 509, 539, 756, 780, 851, 987, 1218, 1227, 1251`.

## Security and operating rules

- The OpenRouter key belongs only in ignored `backend/.env` as `OPENROUTER_API_KEY`.
- The browser never receives the key.
- Manual comparison saving is off by default and writes only to ignored `data/local/manual/` when enabled.
- Local benchmark runs live in ignored `data/local/runs/`.
- The committed demo artifact contains sanitized public benchmark evidence only.
- The request cap is a project-side safety control. It was raised locally from 40 to 50 only to finish the time-sensitive run; that local setting is ignored by Git.

## Tests and release status

The repository contains backend unit and integration coverage for filtering, adapter normalization, scoring, persistence, resumability, API behavior, and sanitization. The frontend has unit tests and Playwright smoke coverage. GitHub Actions checks backend linting, types, tests, frontend tests, production build, OpenAPI drift, and secret patterns.

The final release passed CI: [GitHub Actions run 36873635791](https://github.com/mian-abd/Snr/actions/runs/36873635791). The release also includes a 21-second walkthrough video.

## What comes next

Checkpoint 1 intentionally stops before automatic routing. The next checkpoint can add a learned or rule-based routing policy, additional evaluation tasks, confidence handling, and a broader benchmark only after this evidence layer is accepted.
