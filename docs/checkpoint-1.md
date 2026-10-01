# Checkpoint 1 protocol

Checkpoint 1 establishes the evidence layer that a later adaptive router will consume. It does not choose a model for the user.

## Fixed model identities

- `google/gemma-4-26b-a4b-it:free`
- `nvidia/nemotron-3-ultra-550b-a55b:free`

The runtime loads a committed registry snapshot. Before a live comparison or benchmark it verifies both exact IDs, their text-output capability, free pricing, and context length against OpenRouter. Drift stops the run rather than silently changing the experiment.

## Eligibility demonstration

The only exposed hard requirement is `min_context_tokens`. At the demonstration value of 500,000, the 262,144-token Gemma entry is excluded and the 1,000,000-token Nemotron entry remains eligible. The filter is a pure function over registry metadata.

## Benchmark

The benchmark uses 12 fixed rows from the official GSM8K test split. The source revision, complete source-file checksum, selection seed, and row indices are stored beside the sample.

Each model receives the same system message, prompt template, temperature 0, and 512-token output limit. Only one benchmark request is in flight at a time; model order alternates by question. A logical cell permits at most two attempts and only retryable failures receive a second attempt.

The scorer checks `FINAL_ANSWER`, then a boxed value, then the final standalone number. Values are parsed as decimals and scored by exact numeric equality. An extraction failure receives zero. There is no model judge.

## Evidence layout

Local runs are ignored by Git and contain:

- `manifest.json`
- `attempts.jsonl`
- `results.jsonl`
- `summary.json`

The completed run is sanitized into `data/demo/checkpoint-1`. Sanitization removes provider request IDs and machine-specific details while preserving prompts, responses, measurements, settings, model IDs, and checksums.

## Limitations

Twelve questions are sufficient to demonstrate an auditable end-to-end experiment, not to establish a statistically reliable general ranking. Free endpoints can be rate limited or retired. The checkpoint records these conditions instead of hiding them.
