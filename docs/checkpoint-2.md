# Checkpoint 2: transparent routing policy

Checkpoint 2 builds on the reproducible evidence layer released for Checkpoint 1. It adds a small, inspectable policy layer, a second dated model pool, and a results dashboard, without changing the Checkpoint 1 model identities, GSM8K sample, prompt template, scorer, or stored experiment records.

## Proposal commitments for October 22

| Proposal commitment | Where it is demonstrated |
| --- | --- |
| Two fixed-model baselines and a simple rule-based router on the same benchmark data, compared on accuracy, response time, and cost | Route → Results dashboard (six strategies replayed over the same saved matrix, for either pool) |
| The same prompt routed differently when the user changes priority | Route → Preview decision (Lower cost vs. Higher quality) and the policy acceptance matrix |
| A basic results dashboard showing the selected model and summary results | Route → Results dashboard and Per-prompt routing decisions |

## Two model pools

The Route view has a pool selector. Each pool has its own frozen registry snapshot, acceptance cases, and saved evidence matrix.

| Pool | Registry snapshot | Models | Saved matrix |
| --- | --- | --- | --- |
| Checkpoint 1 free pool | `data/registry/openrouter-2026-09-30.json` | `google/gemma-4-26b-a4b-it:free`, `nvidia/nemotron-3-ultra-550b-a55b:free` | `data/demo/checkpoint-1/` (24 cells) |
| Checkpoint 2 paid pool | `data/registry/openrouter-paid-2026-10-22.json` | `google/gemma-4-26b-a4b-it`, `inception/mercury-3`, `google/gemini-4-argon` | `data/demo/checkpoint-2-paid/` (36 cells) |

The paid snapshot records each model's catalog price and context length. Before any live paid call, the catalog preflight compares the live price and context length against the snapshot as decimals and fails closed on drift.

## Routing policy

Before any priority is applied, the deterministic eligibility filter removes models below the requested minimum context length. A preference only ever chooses among eligible models.

| Priority | Free pool (`rule_based_v1`) | Paid pool (`rule_based_paid_v1`) |
| --- | --- | --- |
| Lower cost | Gemma (free) | Gemma 4 26B, the lowest-price model |
| Higher quality | Nemotron | Gemini 4 Argon, the highest-capability model |
| Faster response | Gemma (free) | Mercury 3, the designated low-latency model |
| Balanced | Any higher-effort signal → Nemotron, otherwise Gemma | 0 signals → Gemma, 1–2 signals → Mercury, 3 or more → Gemini |

Higher-effort signals are `math`, `code`, `long_prompt` (45 or more words), and `many_numbers` (4 or more numeric values). The decision lists the detected signals and a human-readable reason. When the preferred model is filtered out by a hard requirement, the next eligible model in registry order is chosen; both registries are ordered from lowest to highest price, and the reason says the preference was overridden.

The paid-pool tiers reuse the Checkpoint 1 signal definitions unchanged. The three-signal threshold was written before the paid matrix finished and was not tuned against its outcomes.

The decision-preview endpoint evaluates the policy without a credential or provider request. The live route endpoint makes exactly one generation request to the selected model after credential and catalog preflight. It never silently substitutes a different model.

## Policy acceptance matrices

`GET /api/v1/routing/validation?pool=baseline|paid` runs fixed, provider-free reference cases and the Route view shows expected versus actual selections.

- Free pool, 5 cases: cost, latency, quality, balanced math, and the 500,000-token override (Gemma excluded, Nemotron selected).
- Paid pool, 7 cases: cost, latency, quality, balanced general (0 signals), balanced moderate (1 signal), balanced complex (3 signals), and the 500,000-token override (Gemma excluded, the cost preference falls to Mercury).

These are deterministic policy checks, not a quality benchmark.

## Paid benchmark matrix

`python -m app.benchmarks.paid_matrix` collects the paid matrix with the same 12 GSM8K questions (seed 498), prompt template `gsm8k-cp1-v1`, temperature 0, 512 maximum tokens, retry rules, and exact numeric scorer as Checkpoint 1. It prints a worst-case cost estimate, refuses to run above a $1 cap, and requires `--confirm` before spending.

Committed run: `gsm8k-paid-full-20261023T044929Z-5f90eace`. The worst-case estimate was $0.137; actual provider-reported spend was about $0.023.

| Model | Correct | Served | Median latency | Cost |
| --- | ---: | ---: | ---: | ---: |
| Gemini 4 Argon | 12/12 | 12/12 | 4,992 ms | $0.020892 |
| Gemma 4 26B | 11/12 | 12/12 | 2,941 ms | $0.001035 |
| Mercury 3 | 10/12 | 10/12 | 579 ms | $0.000900 |

Mercury's two failures (GSM8K #1227 and #1251) were empty provider responses, recorded as `invalid_response` and kept in the denominator.

## Results dashboard

`GET /api/v1/routing/dashboard?pool=baseline|paid` replays six strategies over the selected pool's saved matrix with no provider calls:

1. Fixed baseline: lowest-cost model.
2. Fixed baseline: higher-capability model.
3. Rule router: cost priority.
4. Rule router: quality priority.
5. Rule router: latency priority.
6. Rule router: balanced priority.

For each strategy it reports selected-model counts, correct answers, served cells, accuracy, median latency, p95 latency (nearest rank), total cost, and cost per correct answer. Below the table, the per-prompt view shows, for any chosen strategy, the selected model, the reason, the outcome, latency, and cost for each question, next to every saved model outcome for that question.

Paid-pool replay:

| Strategy | Models selected | Correct | Median | p95 | Total cost | Cost / correct |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Fixed: lowest-cost | Gemma × 12 | 11/12 | 2,941 ms | 17,992 ms | $0.00104 | $0.000094 |
| Fixed: higher-capability | Gemini × 12 | 12/12 | 4,992 ms | 8,772 ms | $0.02089 | $0.00174 |
| Rule: cost | Gemma × 12 | 11/12 | 2,941 ms | 17,992 ms | $0.00104 | $0.000094 |
| Rule: quality | Gemini × 12 | 12/12 | 4,992 ms | 8,772 ms | $0.02089 | $0.00174 |
| Rule: latency | Mercury × 12 | 10/12 | 579 ms | 1,098 ms | $0.00090 | $0.000090 |
| Rule: balanced | Mercury × 7, Gemini × 5 | 12/12 | 823 ms | 8,772 ms | $0.01156 | $0.00096 |

On this matrix the balanced rule matched the always-Gemini baseline's 12/12 for about 45% less cost and a roughly six times faster median. Mercury's two failures happened on prompts the rule had already sent to Gemini, which favored the balanced strategy. With 12 prompts from one task family this is evidence for this setup, not a general ranking.

Free-pool replay keeps the Checkpoint 1 picture: the fixed stronger baseline is 8/12 with 12/12 served; the fixed smaller baseline is 3/12 with only 3/12 served because of nine shared free-tier rate limits.

## Limits

This checkpoint is a transparent baseline rather than a trained policy. Prompt signals are hand-written keyword and length rules, and priorities map to designated model roles rather than predicted success. The 12-question GSM8K sample is a functional checkpoint, not a statistically significant leaderboard. Prices and availability are dated snapshots.

## Demo path

1. Open **Route** with the **Checkpoint 2 paid pool** selected and show the 7/7 acceptance matrix.
2. Keep the same prompt, preview **Lower cost** (Gemma) and then **Higher quality** (Gemini Argon). No provider call is made.
3. Select **Lower cost**, click **Use 500,000 demo**, and preview. Gemma is excluded first; Mercury is selected and the reason explains the override.
4. Set the minimum context back to 1 and click **Route prompt** for one real paid call with response, latency, tokens, and provider-reported cost.
5. Scroll to the results dashboard and walk through the six strategies.
6. Choose **Rule router: balanced priority** in the per-prompt view and show the model and reason for individual questions.
7. Switch to **Checkpoint 1 free pool** to show the same strategies over the original 24-cell evidence.
