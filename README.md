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
- Collect the paid matrix with `uv run --project backend python -m app.benchmarks.paid_matrix`, which prints a worst-case cost estimate, enforces a $1 cap, and only spends with `--confirm`.

Checkpoint 2 is deliberately a simple, rule-based policy—not a learned router or a claim of statistically conclusive model rankings.

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
