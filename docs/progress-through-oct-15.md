# Original proposal schedule completed through October 15

This document maps the implemented repository state to the October milestones in the original project proposal.

## Week of October 1

- Completed and presented the Checkpoint 1 evidence layer.
- Built the dual-model comparison flow for two pinned OpenRouter model identities.
- Added normalized response, latency, token, cost, and failure fields.
- Added the versioned registry and minimum-context eligibility filter.
- Completed and saved the fixed 12-question GSM8K matrix with 24 logical cells.
- Preserved provider failures, resumable run state, sanitized evidence, tests, CI, documentation, and the tagged Checkpoint 1 release.

## Week of October 8

- Implemented fixed routing baselines for the smaller and stronger models.
- Implemented an explicit rule router with lower-cost, higher-quality, faster-response, and balanced priorities.
- Kept hard requirements separate from routing preferences.
- Added policy and decision contracts containing the selected model, eligible and excluded candidates, task signals, policy version, and human-readable reason.
- Added an offline strategy-replay service that evaluates strategies against the committed Checkpoint 1 result matrix without new model calls.
- Added backend tests for fixed policies, task signals, requirements, explanations, and replay metrics.

## Week of October 15

- Completed the Checkpoint 2 Route interface and explanation view.
- Added a no-provider-call decision preview endpoint and UI action.
- Added the minimum-context control and a 500,000-token demonstration preset.
- Verified that the same prompt changes selection under different priorities.
- Verified that a hard 500,000-token requirement overrides a lower-cost preference by excluding Gemma and selecting Nemotron.
- Completed the strategy dashboard with selected-model counts, accuracy, availability, mean latency, and known cost.
- Updated API contracts, OpenAPI schema, generated frontend types, tests, and documentation.
- Completed the Checkpoint 2 presentation deck, speaking script, live-demo guide, and backup walkthrough recording.

## October 22 checkpoint update

- Added a dated three-model paid pool (Gemma 4 26B, Mercury 3, Gemini 4 Argon) beside the preserved free pool, with live price and context drift checks.
- Collected the first paid model-by-prompt matrix: the same 12 GSM8K questions and protocol, 36 cells, about $0.023 spent against a $1 cap.
- Extended the dashboard with median and p95 latency, cost per correct answer, and per-prompt decisions with reasons.
- Added three-tier balanced routing for the paid pool and seven paid acceptance cases.
- Rebuilt the presentation deck, re-recorded the backup demo, and rewrote the Checkpoint 2 documents.
- On the paid matrix the balanced rule router matched the always-strongest baseline (12/12) for about 45% less cost and a roughly six times faster median; the documents explain why this small sample is not yet a general result.

## Verification snapshot

- Backend: Ruff, mypy, and 30 pytest tests pass (25 at the October 15 snapshot).
- Frontend: ESLint, 2 Vitest unit tests, production build, and 2 Playwright smoke tests pass.
- Demo URL: `http://127.0.0.1:8000` when `./scripts/demo.ps1` is running.
- Presentation: `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx`.
- Backup video: `docs/demo/checkpoint-2-backup-demo.webm`.

## Scope boundary

Checkpoint 2 remains a transparent baseline. Learned routing, larger multi-task evaluation, calibrated confidence, and statistically stronger claims belong to the next phase. The fixed and rule policies remain necessary comparison baselines for that work.
