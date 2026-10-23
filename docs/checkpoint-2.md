# Checkpoint 2: transparent routing policy

Checkpoint 2 builds on the reproducible evidence layer released for Checkpoint 1. It adds a small, inspectable policy layer without changing the fixed model identities, GSM8K sample, scorer, or stored experiment records.

## What is implemented

The application now has a **Route** section with four priorities:

- **Lower cost** selects the smaller baseline, Gemma.
- **Higher quality** selects the stronger baseline, Nemotron.
- **Faster response** selects the smaller baseline as an explicit latency-oriented baseline.
- **Balanced** uses simple visible prompt signals: math, code, long prompts, and prompts with multiple numeric values select Nemotron; other prompts select Gemma.

Before any priority is applied, the existing deterministic eligibility filter removes models that do not meet a requested minimum context length. This preserves the distinction between a hard requirement and a user preference.

The local decision-preview endpoint evaluates the same policy without a credential or provider request, so a user can inspect how a priority and minimum-context requirement change the choice. The live route endpoint makes exactly one generation request to that selected fixed model. It still performs the existing credential and catalog-drift preflight first. It never silently substitutes a different model.

## Deterministic policy acceptance matrix

The Route view also runs five fixed, provider-free acceptance cases and displays expected versus actual selections. The cases cover cost, latency, and quality priorities, the balanced policy's math signal, and the 500,000-token hard-requirement override. The same report is available from `GET /api/v1/routing/validation`.

The matrix is a deterministic policy check, not a quality benchmark. It exists so the checkpoint can show that the implemented rules behave as documented even when shared free-model capacity is unavailable.

## Baselines and replay

The dashboard replays six strategies against the committed Checkpoint 1 GSM8K matrix:

1. Always select the lower-cost/smaller baseline.
2. Always select the stronger baseline.
3. Rule policy with lower-cost priority.
4. Rule policy with higher-quality priority.
5. Rule policy with faster-response priority.
6. Rule policy with balanced priority.

Replay is offline: it reads `data/demo/checkpoint-1/results.jsonl` and selects records from the saved 24 logical cells. It makes no OpenRouter call, so the table remains available even when free provider capacity is unavailable.

For each strategy, the dashboard shows model selections, exact numeric GSM8K accuracy, served-cell availability, mean successful latency, and known cost. Failed or rate-limited cells remain part of the denominator, so the display does not hide reliability constraints.

## Limits

This checkpoint is a transparent baseline rather than a trained policy. The prompt signals are deliberately small and easy to explain; they are not a quality predictor. The 12-question GSM8K sample is a functional project checkpoint, not a statistically significant leaderboard. Future work can replace or augment this policy with calibrated routing, more tasks, richer constraints, and larger evaluations after evaluating against the same kind of preserved evidence.

## Demo path

1. Open **Route** and show the five-case acceptance matrix passes without a key or provider call.
2. Change between **Lower cost** and **Higher quality**, click **Preview decision**, and show the selected fixed model changes for the same prompt without a provider call.
3. Set the minimum context to `500000`, preview again, and explain that the hard requirement excludes Gemma before it can satisfy a lower-cost preference.
4. Show the strategy table, which replays the saved 24-cell matrix without a provider call.
5. If provider capacity is available, click **Route prompt** to show one real request and the recorded status, response, latency, token usage, and cost.
6. Use the Benchmark section to return to the raw Checkpoint 1 evidence that powers the replay.
