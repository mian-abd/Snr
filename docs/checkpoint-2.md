# Checkpoint 2: transparent routing policy

Checkpoint 2 builds on the reproducible evidence layer released for Checkpoint 1. It adds a small, inspectable policy layer without changing the fixed model identities, GSM8K sample, scorer, or stored experiment records.

## What is implemented

The application now has a **Route** section with four priorities:

- **Lower cost** selects the smaller baseline, Gemma.
- **Higher quality** selects the stronger baseline, Nemotron.
- **Faster response** selects the smaller baseline as an explicit latency-oriented baseline.
- **Balanced** uses simple visible prompt signals: math, code, long prompts, and prompts with multiple numeric values select Nemotron; other prompts select Gemma.

Before any priority is applied, the existing deterministic eligibility filter removes models that do not meet a requested minimum context length. This preserves the distinction between a hard requirement and a user preference.

The live route endpoint makes exactly one generation request to the selected fixed model. It still performs the existing credential and catalog-drift preflight first. It never silently substitutes a different model.

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

1. Open **Route**. The strategy table loads from the saved matrix with no key or live model request.
2. Change between **Lower cost** and **Higher quality** to show the selected fixed model changes for the same prompt.
3. Explain that hard context requirements run first and can override a preference.
4. If provider capacity is available, click **Route prompt** to show a single real request and the recorded status, response, latency, token usage, and cost.
5. Use the Benchmark section to return to the raw Checkpoint 1 evidence that powers the replay.
