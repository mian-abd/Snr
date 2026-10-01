# Sanitized Checkpoint 1 evidence

This directory contains the real, sanitized Checkpoint 1 benchmark exported from
`gsm8k-full-20261001T134908Z-0b94a2ed`.

- 12 fixed GSM8K questions × 2 pinned models = 24 canonical records
- Nemotron: 12 successful calls, 8 exact matches
- Gemma: 3 successful calls, 3 exact matches, and 9 upstream shared-pool rate limits
- Reported cost: $0 for both free endpoints

The Gemma failure states are intentionally preserved. They are part of the observed provider
behavior and must not be interpreted as nine incorrect mathematical answers. This small benchmark
demonstrates the collection, scoring, filtering, failure, and recovery pipeline; it is not a
statistically conclusive model ranking.

`manifest.json`, `results.jsonl`, and `summary.json` retain public prompts, responses, settings,
measurements, model IDs, and checksums. Provider request IDs, account identifiers, credentials,
authorization data, and machine-specific paths are removed. Results are never fabricated to make
the interface appear complete.
