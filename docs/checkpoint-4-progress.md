# Week of November 19: final evaluation, error analysis, robustness, export

This records the proposal's work-plan items for the week of November 19. The week of November 26 (final robustness runs and plots, finished export and data validation, the final report) is not started; see [what is left](#left-for-the-week-of-november-26).

| Proposal item | Status |
| --- | --- |
| Complete the held-out evaluation | Done: the frozen router on the Checkpoint 3 test split (with intervals added) and on 300 fresh prompts answered on 2026-11-13 and 14 ([details](#the-final-held-out-set), [results](#results)) |
| Finish the oracle and under-routing/over-routing analysis | Done: per priority and task, with a stricter "dominated" count, the extra cost, regret, and worked examples ([details](#oracle-gap-and-routing-errors)) |
| Implement robustness tests for changed price, latency, reliability, and user priorities | Done: a replay engine with 9 scenarios per evaluation and a priority sweep, plus a stress test on the Router page ([method](#robustness-tests), [results](#robustness-results)) |
| Begin experiment export and final interface cleanup | Done for this week: seven tables as CSV or JSON from the site and the CLI; the console rebuilt as a public research site ([details](#export-and-interface)) |
| Owner decisions on 2026-11-13 | Check the live catalog; keep the Checkpoint 2 rule router (now in the Lab, as a baseline); retry the two keyed models once (still failing, so excluded); draw a fresh final set |

## Results in brief

All numbers are on the 300 fresh prompts unless the original 120-prompt test split is named. Intervals are 95% bootstrap intervals; p-values are Holm-adjusted.

1. **The frozen router still predicts well on prompts drawn after it was frozen.** Its log loss is 0.365 against 0.368 for the model x task table (ROC AUC 0.703 against 0.693); on the original split it was 0.432 against 0.434. The fresh prompts were somewhat easier for every model (always using Gemini 4 Argon: 94.7% against 93.3%; always using Gemma 4 26B: 89.3% against 85.8%), so strategies are compared within a set, not across sets.
2. **Best quality saves money for nearly the same accuracy.** 282 right for $0.964, against 284 for $1.164 when every prompt goes to Gemini 4 Argon: 17% cheaper (13% to 22%), with an accuracy difference of -0.7 points (95% CI -1.7 to +0.0; Holm p = 1.00). On the original split it was 112 against 112 for 15% less. Almost all of the saving comes from math, which goes to Gemma 4 26B (96 of 100 right against Gemini's 98, for $0.0067 instead of $0.20).
3. **Lowest cost is almost free.** 265 right for $0.0034, mostly on Nemotron 3 Ultra (free) and gpt-oss-120b, against 268 for $0.035 when every prompt goes to the cheapest paid model: 90% cheaper (86% to 94%), accuracy -1.0 points (95% CI -3.7 to +1.7; p = 1.00).
4. **The fastest setting does not beat the rule router.** On the fresh prompts both got 276 right, but the adaptive router was 1.1 s slower at the median (95% CI 0.5 to 1.7 s) and cost 1.10 times as much (0.81 to 1.49). On the original split it was 1.45 s faster and 38% cheaper but got 3 fewer right (not significant). It sends 91 of the 100 code prompts and 22 knowledge questions to Gemini 4 Argon, which is accurate but slow; the rule router sends 54 and 9 there and the rest to Gemma.
5. **The prompt features add nothing measurable on these benchmarks.** The model x task reference, which knows only each model's per-task success rate, ties the router at best quality (282 vs 282) and is two answers ahead at lowest cost (267 vs 265, p = 1.00). Which model to use depends on the task, not on details of the prompt. Benchmark prompts within a task are alike; varied real traffic is where prompt features could matter.
6. **The live catalog check is the largest effect measured.** Mercury 3 was retired on November 12. Without the check, the fastest and balanced settings sent 211 of 300 prompts to it and got 83 right; with it, 276: +64.3 points (95% CI +59.0 to +69.7; p < 0.001). The rule router, still calling Mercury, got 134.
7. **There is room left.** A hindsight oracle gets 286 right for $0.045. The best-quality router's regret is only 4 answers, but it over-routes: on 276 prompts a model it expected to be cheaper was also right, which cost $0.806 extra. At lowest cost the regret is 17 answers: 21 of its 35 wrong answers were avoidable (some model got them right), 16 of them knowledge and code questions given to Nemotron 3 Ultra (free).
8. **Robustness: price and availability changes work, reliability and normalization need fixing.** Told that a price changed or a model was retired, the router reprices and reroutes, staying within two right answers of its old choices. But the tuned priorities give reliability no weight, so a 50% outage of the free endpoints halves the lowest-cost accuracy (137 of 300) even when the router knows about it; with the reliability weight at 1 it holds 268. Cost and time are scored relative to the most expensive and slowest model available, so telling the router that the slowest models got three times slower made the fastest setting slower (7.1 s instead of 3.8 s).

## Owner decisions (2026-11-13)

1. **Final evaluation set:** draw about 300 fresh prompts nobody has used, run the models still available on them, and evaluate the frozen router under real provider drift. More models could be added if needed; none were (see [the two keyed models](#the-two-keyed-models-retried-once)).
2. **Provider drift:** check the live catalog at startup. A retired model becomes unavailable (a failed hard requirement, with the reason shown), changed prices update expected costs, and the app falls back to the dated snapshot when the check fails.
3. **Checkpoint 2 tab:** keep it as history, and make its refusal message explain what changed. It now lives on the site's Lab page, presented as the rule-based baseline.
4. **Keyed models:** retry Gemma 4 31B and DeepSeek V4.1 Flash once; add them only if healthy.

## Live catalog check

`backend/app/registry/live_catalog.py` asks each provider what it serves now, for the learned router's nine models:

- **OpenRouter:** `GET /api/v1/models/{model}/endpoints` (public, no key) lists every host with its price. A model is unavailable when none of its pinned hosts serves it, and its live price is the highest price among the pinned hosts that still do, the snapshot's own rule.
- **OVHcloud and Ollama:** their OpenAI-compatible `/models` lists. A local model is unavailable when nothing answers on the Ollama port.
- **Only a positive answer removes a model.** A check that fails leaves the model as the snapshot describes it; when every check fails, the status falls back to the snapshot and says so.

The server runs the check at startup (at most 12 seconds, then the snapshot), keeps the result, and exposes it at `GET /api/v1/learned/catalog`; `POST /api/v1/learned/catalog/refresh` checks again. The router then:

- excludes an unavailable model before scoring, with the reason ("Unavailable now: OpenRouter lists inception/mercury-3 but no host serves it any more (retired)");
- scales a model's expected cost to the live price at the prompt's token mix (`live_expected_cost`), and shows the old value;
- adds to its reason which model it would have chosen without the check.

The classifier and the tuned weights are never changed by the check. Without a catalog the router behaves exactly as evaluated at Checkpoint 3, which the tests and the parity check below confirm.

What the check found on 2026-11-13 (saved as `data/registry/live-catalog-2026-11-13.json`):

| Model | Live status |
| --- | --- |
| Mercury 3 | Unavailable: OpenRouter lists it, but no host serves it |
| Gemma 4 26B A4B | Price cut again on the pinned NextBit host: $0.0765 / $0.255 → $0.0675 / $0.225 per million input / output tokens (−11.8%) |
| DeepSeek V4 Flash | Pinned host Crusoe no longer serves it; Parasail and DeepInfra do, at the snapshot's price |
| The other six | Served as in the snapshot |

The Checkpoint 2 rule route keeps its own all-or-nothing check (`backend/app/registry/loader.py`). Its refusal now lists every change in one message instead of stopping at the first: Mercury 3 retired, and Gemma's price moved from $0.09 / $0.3 to $0.0675 / $0.225 per million tokens since its 2026-10-23 snapshot. It ends: "This route fails closed instead of sending a prompt to a model or price it was not validated against; it is kept unchanged as the baseline the adaptive router is measured against."

Errors the providers return now read correctly: a 404 says the provider does not serve the model on that route and it may be retired, a 401 that the key was rejected, and a 402 that the account has no credit. All three used to say "temporarily unavailable or overloaded".

## The two keyed models, retried once

`python -m app.benchmarks.suite_runner --models gemma-4-31b,deepseek-v4.1-flash --smoke 2 --run-id cp3-smoke-keyed4 --confirm`, 8 prompts each:

- **Gemma 4 31B (Google AI Studio, free):** 5 of 8 answered; 8 of 13 attempts failed with HTTP 500 or 503 ("overloaded").
- **DeepSeek V4.1 Flash (NVIDIA NIM, free):** 1 of 8 answered; 15 of 16 attempts timed out after 180 s.

Both are as unreliable as on October 27 and November 3, so they stay out of the pool and the router, as agreed. Both models are also sold on OpenRouter (at $0.20 / $0.40 and $0.05 / $0.20 per million tokens), which would be the way to add them as a "new model joins the pool" scenario. The frozen router cannot route to a model it has no outcomes for (model identity is a feature), so that would need a retrained router; the proposal does not ask for it.

## The final held-out set

`python -m app.benchmarks.prepare_final` draws the set from the same four pinned, checksum-verified sources as the 600-prompt suite, with its own seed (20261119):

- **300 prompts:** 100 GSM8K, 100 MMLU-Pro (stratified across the 14 subjects), 50 HumanEval+, and 50 MBPP+.
- **Never used before:** every prompt in the 600-prompt suite and Checkpoint 1's 12 GSM8K questions are excluded. HumanEval+ had only 64 unused tasks, so 50 is near its limit.
- **Fixed first:** the file (`data/benchmarks/final_heldout.jsonl`) and its SHA-256 were written before any model answered it, every run manifest repeats the hash, and rebuilding it reproduces the same bytes.
- **Its own split:** `RouterSplit.FINAL`, so it can never enter the training history.

`python -m app.benchmarks.suite_runner --suite final --confirm` ran it on 2026-11-13 and 14 through the nine models the router knows, with the same prompts, token caps, temperature 0, timeouts, retries, and pacing as the suite. Mercury 3 was run too: its 300 calls are the router's real view of a retired model (HTTP 404, in about 0.1 s). Code answers were scored by EvalPlus in the same locked-down Docker container (`python -m app.benchmarks.code_scoring --suite final --run-id final-heldout`).

## Final evaluation method

`python -m app.learned.final_eval` evaluates `data/learned/cp3-router-model.json` exactly as exported at Checkpoint 3. Nothing is retrained or retuned.

- **Two evaluations:** the Checkpoint 3 test split (120 prompts, measured in late October, before the drift) and the final set (300 prompts, measured after it). On the final set the router applies the live catalog of 2026-11-13.
- **Parity check:** every Checkpoint 3 strategy result, and the test log loss, must come out exactly as the Checkpoint 3 report has them, or the script stops.
- **Strategies:** always cheapest paid (Gemma 4 26B), always strongest (Gemini 4 Argon), the Checkpoint 2 rule router, the learned router per priority, the model × task reference per priority, and the oracle per priority. On the final set, two more rows show the drift without the catalog check: the learned router, and the rule router, still calling Mercury 3.
- **The rule router after drift:** when its fast model is gone it falls back the way its own code does (the first eligible model in its registry order, Gemma). Live, the Checkpoint 2 route refuses to run at all instead.
- **Intervals:** 95% percentile-bootstrap intervals over prompts, 10,000 resamples, one fixed seed, with the same resampled prompts for every strategy.
- **Paired tests:** McNemar's exact test for correctness (only the prompts where exactly one of the two is right count), paired-bootstrap intervals for accuracy, cost, and latency differences, and Holm's adjustment across each evaluation's family. The family was written in code before the final results were read:
  1. learned quality vs always strongest;
  2. learned lower cost vs always cheapest paid;
  3. learned faster response vs the rule router;
  4. learned balanced vs the rule router;
  5. learned quality vs the model × task reference;
  6. learned lower cost vs the model × task reference;
  7. on the final set only: learned faster response and balanced, with and without the catalog check.
- **Committed inputs:** `data/learned/cells.jsonl` holds every scored outcome (8,100 rows: model, prompt, status, correct, latency, cost, output tokens; no prompts, responses, or request IDs), so a clone reproduces the report without the raw runs. `--from-runs` rebuilds it from the local runs.
- **Outputs:** `data/learned/final-evaluation.json`, `data/learned/final-decisions.jsonl` (every strategy's choice and outcome on every prompt), and `docs/figures/final-heldout-accuracy-{cost,latency}.{png,svg}`.

## Results

The full report is `data/learned/final-evaluation.json`; the figures are `docs/figures/final-heldout-accuracy-cost.svg` and `final-heldout-accuracy-latency.svg`. The parity check passed: every Checkpoint 3 strategy result and the test log loss came out exactly as reported at Checkpoint 3.

### The models on the fresh prompts

Mercury 3's 300 calls all failed (HTTP 404: retired). Failed calls count as wrong; the unusable responses of DeepSeek V4 Flash, Nemotron 3 Ultra, and Qwen 3.8 27B (16, 15, and 36) were cut off at the token limit, except one empty answer.

| Model | Correct | Math | Knowledge | Code | Failed calls | Median time | Billed cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemini 4 Argon | 284/300 | 98/100 | 92/100 | 94/100 | 0 | 8.10 s | $1.164 |
| Gemma 4 26B | 268/300 | 96/100 | 83/100 | 89/100 | 0 | 2.03 s | $0.035 |
| Nemotron 3 Ultra (free) | 266/300 | 95/100 | 85/100 | 86/100 | 15 | 7.40 s | $0 |
| DeepSeek V4 Flash | 262/300 | 95/100 | 79/100 | 88/100 | 16 | 2.95 s | $0.072 |
| gpt-oss-120b | 259/300 | 96/100 | 82/100 | 81/100 | 0 | 3.84 s | $0 |
| Qwen 3.8 27B | 253/300 | 96/100 | 73/100 | 84/100 | 36 | 6.52 s | $0 |
| Llama 3.3 70B | 247/300 | 95/100 | 76/100 | 76/100 | 0 | 10.54 s | $0 |
| Qwen 3.5 9B (local) | 242/300 | 96/100 | 75/100 | 71/100 | 0 | 6.91 s | $0 |
| Mercury 3 | 0/300 | 0/100 | 0/100 | 0/100 | 300 | — | $0 |

### Original test split (120 prompts, answered in late October)

| Strategy | Correct | Accuracy (95% CI) | Billed cost (95% CI) | Median time (95% CI) |
| --- | ---: | --- | --- | --- |
| Always cheapest paid (Gemma 4 26B) | 103 | 85.8% (79.2%–91.7%) | $0.018 ($0.016–$0.021) | 5.13 s (4.67 s–5.83 s) |
| Always strongest (Gemini 4 Argon) | 112 | 93.3% (88.3%–97.5%) | $0.493 ($0.413–$0.582) | 5.12 s (4.71 s–5.86 s) |
| Rule router | 105 | 87.5% (81.7%–93.3%) | $0.186 ($0.127–$0.253) | 3.53 s (2.46 s–4.31 s) |
| Adaptive router, lowest cost | 103 | 85.8% (79.2%–91.7%) | $0.0003 ($0–$0.0008) | 12.70 s (11.00 s–16.38 s) |
| Model x task reference, lowest cost | 104 | 86.7% (80.8%–92.5%) | $0 ($0–$0) | 13.35 s (11.11 s–17.36 s) |
| Adaptive router, best quality | 112 | 93.3% (88.3%–97.5%) | $0.421 ($0.332–$0.518) | 5.36 s (4.69 s–6.03 s) |
| Model x task reference, best quality | 111 | 92.5% (87.5%–96.7%) | $0.420 ($0.330–$0.517) | 6.48 s (6.20 s–7.38 s) |
| Adaptive router, fastest | 102 | 85.0% (78.3%–90.8%) | $0.116 ($0.085–$0.150) | 2.09 s (1.58 s–3.43 s) |
| Model x task reference, fastest | 104 | 86.7% (80.0%–92.5%) | $0.127 ($0.097–$0.161) | 2.56 s (1.78 s–3.64 s) |
| Adaptive router, balanced | 102 | 85.0% (78.3%–90.8%) | $0.116 ($0.085–$0.150) | 2.09 s (1.58 s–3.43 s) |
| Model x task reference, balanced | 104 | 86.7% (80.0%–92.5%) | $0.127 ($0.097–$0.161) | 2.56 s (1.78 s–3.64 s) |
| Oracle, lowest cost | 113 | 94.2% (90.0%–98.3%) | $0.0007 ($0–$0.0020) | 16.05 s (13.04 s–21.14 s) |
| Oracle, best quality | 116 | 96.7% (93.3%–99.2%) | $0.017 ($0.0078–$0.029) | 4.22 s (3.37 s–5.05 s) |
| Oracle, fastest | 116 | 96.7% (93.3%–99.2%) | $0.058 ($0.029–$0.098) | 1.68 s (1.31 s–1.97 s) |
| Oracle, balanced | 116 | 96.7% (93.3%–99.2%) | $0.058 ($0.029–$0.098) | 1.68 s (1.31 s–1.97 s) |

| Question | Correct | Only one right | Accuracy difference (95% CI) | Cost ratio (95% CI) | Median time difference (95% CI) | Holm p |
| --- | --- | --- | --- | --- | --- | ---: |
| Is the best-quality setting as accurate as always using the strongest model, for less? | 112 vs 112 | 0 vs 0 | +0.0 pts (+0.0 to +0.0) | 0.85 (0.79–0.90) | +0.24 s (-0.15 to +0.65) | 1.00 |
| Is the lowest-cost setting as accurate as always using the cheapest paid model, for less? | 103 vs 103 | 7 vs 7 | +0.0 pts (-5.8 to +5.8) | 0.02 (0.00–0.05) | +7.57 s (+5.92 to +10.80) | 1.00 |
| Is the fastest setting quicker than the rule-based router without losing accuracy? | 102 vs 105 | 1 vs 4 | -2.5 pts (-5.8 to +0.8) | 0.62 (0.44–0.88) | -1.45 s (-2.24 to -0.19) | 1.00 |
| Does the balanced setting beat the rule-based router? | 102 vs 105 | 1 vs 4 | -2.5 pts (-5.8 to +0.8) | 0.62 (0.44–0.88) | -1.45 s (-2.24 to -0.19) | 1.00 |
| Do the prompt features add accuracy beyond per-task averages? | 112 vs 111 | 1 vs 0 | +0.8 pts (+0.0 to +2.5) | 1.00 (0.99–1.01) | -1.12 s (-1.96 to -0.52) | 1.00 |
| Do the prompt features help the lowest-cost setting beyond per-task averages? | 103 vs 104 | 0 vs 1 | -0.8 pts (-2.5 to +0.0) | — (both free) | -0.65 s (-2.22 to +0.00) | 1.00 |

### Fresh prompts (300 prompts, answered on 2026-11-13 and 14)

The router applies the live catalog of 2026-11-13, so Mercury 3 is excluded and Gemma 4 26B is repriced. The "no catalog check" rows show what the same router and the rule router would have done without it; their Mercury calls really failed.

| Strategy | Correct | Accuracy (95% CI) | Billed cost (95% CI) | Median time (95% CI) |
| --- | ---: | --- | --- | --- |
| Always cheapest paid (Gemma 4 26B) | 268 | 89.3% (85.7%–92.7%) | $0.035 ($0.032–$0.039) | 2.03 s (1.80 s–2.22 s) |
| Always strongest (Gemini 4 Argon) | 284 | 94.7% (92.0%–97.0%) | $1.164 ($1.043–$1.305) | 8.10 s (7.73 s–8.46 s) |
| Rule router | 276 | 92.0% (88.7%–95.0%) | $0.393 ($0.283–$0.527) | 2.77 s (2.26 s–3.22 s) |
| Rule router, still calling Mercury 3 | 134 | 44.7% (39.0%–50.3%) | $0.377 ($0.266–$0.512) | 0.45 s (0.18 s–1.33 s) |
| Adaptive router, lowest cost | 265 | 88.3% (84.7%–92.0%) | $0.0034 ($0.0020–$0.0048) | 5.74 s (4.91 s–6.60 s) |
| Adaptive router, lowest cost, no catalog check | 267 | 89.0% (85.3%–92.3%) | $0.0013 ($0.0005–$0.0023) | 6.43 s (5.45 s–7.47 s) |
| Model x task reference, lowest cost | 267 | 89.0% (85.3%–92.3%) | $0 ($0–$0) | 6.57 s (5.68 s–7.78 s) |
| Adaptive router, best quality | 282 | 94.0% (91.3%–96.7%) | $0.964 ($0.831–$1.113) | 7.22 s (6.62 s–7.81 s) |
| Adaptive router, best quality, no catalog check | 282 | 94.0% (91.3%–96.7%) | $0.964 ($0.831–$1.113) | 7.22 s (6.62 s–7.81 s) |
| Model x task reference, best quality | 282 | 94.0% (91.3%–96.7%) | $0.962 ($0.829–$1.111) | 7.37 s (6.89 s–7.91 s) |
| Adaptive router, fastest | 276 | 92.0% (88.7%–95.0%) | $0.433 ($0.362–$0.507) | 3.84 s (3.19 s–4.53 s) |
| Adaptive router, fastest, no catalog check | 83 | 27.7% (22.7%–32.7%) | $0.272 ($0.217–$0.328) | 0.15 s (0.14 s–0.16 s) |
| Model x task reference, fastest | 273 | 91.0% (87.7%–94.0%) | $0.323 ($0.268–$0.379) | 3.93 s (3.26 s–4.40 s) |
| Adaptive router, balanced | 276 | 92.0% (88.7%–95.0%) | $0.433 ($0.362–$0.507) | 3.84 s (3.19 s–4.53 s) |
| Adaptive router, balanced, no catalog check | 83 | 27.7% (22.7%–32.7%) | $0.272 ($0.217–$0.328) | 0.15 s (0.14 s–0.16 s) |
| Model x task reference, balanced | 273 | 91.0% (87.7%–94.0%) | $0.323 ($0.268–$0.379) | 3.93 s (3.26 s–4.40 s) |
| Oracle, lowest cost | 282 | 94.0% (91.3%–96.7%) | $0 ($0–$0) | 3.92 s (3.33 s–4.54 s) |
| Oracle, best quality | 286 | 95.3% (93.0%–97.7%) | $0.045 ($0.016–$0.086) | 2.10 s (1.97 s–2.23 s) |
| Oracle, fastest | 286 | 95.3% (93.0%–97.7%) | $0.077 ($0.039–$0.124) | 1.71 s (1.57 s–1.84 s) |
| Oracle, balanced | 286 | 95.3% (93.0%–97.7%) | $0.077 ($0.039–$0.124) | 1.71 s (1.57 s–1.84 s) |

| Question | Correct | Only one right | Accuracy difference (95% CI) | Cost ratio (95% CI) | Median time difference (95% CI) | Holm p |
| --- | --- | --- | --- | --- | --- | ---: |
| Is the best-quality setting as accurate as always using the strongest model, for less? | 282 vs 284 | 0 vs 2 | -0.7 pts (-1.7 to +0.0) | 0.83 (0.78–0.87) | -0.88 s (-1.29 to -0.43) | 1.00 |
| Is the lowest-cost setting as accurate as always using the cheapest paid model, for less? | 265 vs 268 | 6 vs 9 | -1.0 pts (-3.7 to +1.7) | 0.10 (0.06–0.14) | +3.71 s (+2.96 to +4.51) | 1.00 |
| Is the fastest setting quicker than the rule-based router without losing accuracy? | 276 vs 276 | 2 vs 2 | +0.0 pts (-1.3 to +1.3) | 1.10 (0.81–1.49) | +1.07 s (+0.53 to +1.72) | 1.00 |
| Does the balanced setting beat the rule-based router? | 276 vs 276 | 2 vs 2 | +0.0 pts (-1.3 to +1.3) | 1.10 (0.81–1.49) | +1.07 s (+0.53 to +1.72) | 1.00 |
| Do the prompt features add accuracy beyond per-task averages? | 282 vs 282 | 0 vs 0 | +0.0 pts (+0.0 to +0.0) | 1.00 (0.99–1.01) | -0.14 s (-0.28 to +0.00) | 1.00 |
| Do the prompt features help the lowest-cost setting beyond per-task averages? | 265 vs 267 | 1 vs 3 | -0.7 pts (-2.0 to +0.7) | — (both free) | -0.82 s (-1.59 to -0.30) | 1.00 |
| How much does the live catalog check protect the fastest setting from the retired model? | 276 vs 83 | 193 vs 0 | +64.3 pts (+59.0 to +69.7) | 1.59 (1.37–1.90) | +3.69 s (+3.04 to +4.37) | <0.001 |
| How much does the live catalog check protect the balanced setting? | 276 vs 83 | 193 vs 0 | +64.3 pts (+59.0 to +69.7) | 1.59 (1.37–1.90) | +3.69 s (+3.04 to +4.37) | <0.001 |

Fastest and balanced were tuned to the same weights (cost 0.05, latency 1), so their rows are identical. No accuracy difference between the router and a baseline is significant on either set; the only significant accuracy effect is the catalog check. Cost and time differences can still be clear from their paired-bootstrap intervals: best quality is cheaper than always using Gemini 4 Argon on both sets (and faster on the fresh prompts), and the fastest setting is faster than the rule router on the original split but slower on the fresh prompts.

## Oracle gap and routing errors

The oracle picks, with hindsight, the model that maximizes the priority's score given what every model actually did. Against it, every wrong answer of the router is one of:

- **unavoidable:** no model got the prompt right;
- **under-routed:** the router's choice was wrong but a model it expected to cost more was right.

Every right answer can still be **over-routed**: a model the router expected to cost less was also right. It is **dominated** when that cheaper model was also no slower on the actual call. Regret is the oracle's correct answers minus the router's.

### Original test split

| Priority | Wrong | Unavoidable | Under-routed | Over-routed | Of which dominated | Extra cost of over-routing | Oracle correct | Regret |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lowest cost | 17 | 4 | 12 | 1 | 0 | $0.0001 | 113 | 10 |
| best quality | 8 | 4 | 0 | 108 | 87 | $0.386 | 116 | 4 |
| fastest | 18 | 4 | 10 | 99 | 27 | $0.084 | 116 | 14 |
| balanced | 18 | 4 | 10 | 99 | 27 | $0.084 | 116 | 14 |

By task (under-routed / over-routed):

- lowest cost: math 1 / 0; knowledge 6 / 1; code 5 / 0
- best quality: math 0 / 38; knowledge 0 / 39; code 0 / 31
- fastest: math 1 / 37; knowledge 7 / 32; code 2 / 30
- balanced: math 1 / 37; knowledge 7 / 32; code 2 / 30

### Fresh prompts

| Priority | Wrong | Unavoidable | Under-routed | Over-routed | Of which dominated | Extra cost of over-routing | Oracle correct | Regret |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lowest cost | 35 | 14 | 19 | 18 | 11 | $0.0026 | 282 | 17 |
| best quality | 18 | 14 | 2 | 276 | 185 | $0.806 | 286 | 4 |
| fastest | 24 | 14 | 8 | 275 | 147 | $0.400 | 286 | 10 |
| balanced | 24 | 14 | 8 | 275 | 147 | $0.400 | 286 | 10 |

By task (under-routed / over-routed):

- lowest cost: math 2 / 0; knowledge 9 / 18; code 8 / 0
- best quality: math 2 / 96; knowledge 0 / 90; code 0 / 90
- fastest: math 2 / 96; knowledge 6 / 86; code 0 / 93
- balanced: math 2 / 96; knowledge 6 / 86; code 0 / 93

Over-routing is the router's main cost, not under-routing. At best quality the router answered all but 4 avoidable prompts right, but on 276 of 300 a model it expected to be cheaper was also right. It happens on every task: math goes to Gemma 4 26B when a free model was also right (96 prompts), and knowledge and code questions go to Gemini 4 Argon when a cheaper model was also right (180 prompts), which is where nearly all of the extra $0.81 goes ($0.53 on knowledge, $0.27 on code). The router cannot tell in advance which of those prompts a cheaper model will get right. At lowest cost the trade goes the other way: only 18 over-routed prompts, but 19 under-routed ones, where paying more would have bought a right answer.

Worked examples from the fresh prompts (the site shows these on the Research page, with the prompt):

- **Under-routed, lowest cost** (`gsm8k-test-1019`): The router predicted 93% success for gpt-oss-120b, which answered wrong. Gemini 4 Argon, which the router expected to cost more, answered right for $0.00211 in 5.2 s.
- **Under-routed, lowest cost** (`gsm8k-test-1161`): The router predicted 93% success for gpt-oss-120b, which answered wrong. Gemini 4 Argon, which the router expected to cost more, answered right for $0.01427 in 20.6 s.
- **Over-routed, lowest cost** (`mmlu_pro-test-05030`): Gemma 4 26B A4B answered right for $0.00019 in 6.4 s, but gpt-oss-120b, which the router expected to cost less, was also right for $0 (free) in 10.4 s.
- **Over-routed, lowest cost** (`mmlu_pro-test-00914`): Gemma 4 26B A4B answered right for $0.00018 in 17.4 s, but Llama 3.3 70B Instruct, which the router expected to cost less, was also right for $0 (free) in 27.6 s.
- **Over-routed, best quality** (`mmlu_pro-test-08726`): Gemini 4 Argon answered right for $0.01702 in 19.2 s, but gpt-oss-120b, which the router expected to cost less, was also right for $0 (free) in 13.6 s.
- **Over-routed, best quality** (`mmlu_pro-test-04364`): Gemini 4 Argon answered right for $0.01587 in 19.2 s, but gpt-oss-120b, which the router expected to cost less, was also right for $0 (free) in 18.5 s.
- **Over-routed, fastest** (`mmlu_pro-test-06042`): Gemini 4 Argon answered right for $0.01150 in 20.9 s, but Llama 3.3 70B Instruct, which the router expected to cost less, was also right for $0 (free) in 22.6 s.

## Robustness tests

`backend/app/learned/robustness.py` replays the stored outcomes while conditions change, as the proposal describes. A scenario changes two things:

- **The world:** what a call would now cost, how long it would take, or whether it fails. Costs and latencies are rescaled. Injected failures return an error after 2 s and are picked by a fixed hash of (model, prompt), so a larger outage always contains a smaller one. A retired model fails in the 0.1 s its real 404s took.
- **What the router knows:** the *adapted* router is told about the change, as the live catalog (price, availability) or call monitoring (latency, failure rate) would tell it; the *frozen* router keeps its trained estimates. Both use the user's weights. Neither is retrained.

Baselines follow the world but never adapt, and the oracle sees the changed world with perfect hindsight. Each scenario runs on both evaluations; on the final set, hypothetical changes come on top of the live catalog. A test checks that the fast replay chooses exactly what the live router chooses, with and without the catalog, on every preset.

The scenarios:

| Scenario | Condition | Kind |
| --- | --- | --- |
| Mercury 3 retired and Gemma 4 26B 11.8% cheaper | availability, price | Observed (Nov 12–13) |
| Gemma 4 26B costs 30× more (about Gemini's price) | price | What-if |
| Gemini 4 Argon costs 4× more | price | What-if |
| Gemini 4 Argon costs a quarter | price | What-if |
| The three free OVHcloud models 3× slower | latency | What-if |
| Gemma 4 26B 3× slower | latency | What-if |
| The four free remote models fail half their calls | reliability | What-if |
| Same outage, with the reliability weight raised from 0 to 1 | reliability, priorities | What-if |
| Gemini 4 Argon fails 30% of calls, reliability weight 1 | reliability, priorities | What-if |

User priorities are also swept directly: quality weight 1, and the cost or the latency weight varied from 0 to 5 with the other at 0.

### Robustness results

Each cell is correct answers and billed cost (and the median time, for the fastest setting) for the router that is told about the change, then for the one with its old estimates. Balanced matches fastest. The oracle and the baselines see the changed world.

**Fresh prompts (300 prompts).**

| Scenario | Best quality: told / old estimates | Lowest cost: told / old estimates | Fastest: told / old estimates | Oracle (best quality) | Rule router | Always strongest |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Observed drift (Nov 12-13) | 282, $0.964 / 282, $0.964 | 265, $0.0034 / 267, $0.0013 | 276, $0.433, 3.84 s / 83, $0.272, 0.15 s | 286 | 276, $0.393 | 284, $1.164 |
| Gemma 4 26B costs 30x more | 282, $0.962 / 282, $1.160 | 267, $0 / 265, $0.101 | 275, $0.577, 5.63 s / 276, $1.064, 3.84 s | 286 | 276, $1.105 | 284, $1.164 |
| Gemini 4 Argon costs 4x more | 282, $3.820 / 282, $3.835 | 265, $0.018 / 265, $0.0034 | 276, $1.640, 3.80 s / 276, $1.668, 3.84 s | 286 | 276, $1.499 | 284, $4.657 |
| Gemini 4 Argon costs a quarter | 282, $0.239 / 282, $0.246 | 267, $0 / 265, $0.0034 | 276, $0.133, 4.14 s / 276, $0.125, 3.84 s | 286 | 276, $0.117 | 284, $0.291 |
| Free OVHcloud endpoints 3x slower | 282, $0.948 / 282, $0.964 | 265, $0.0034 / 265, $0.0034 | 282, $0.935, 7.11 s / 276, $0.433, 3.84 s | 286 | 276, $0.393 | 284, $1.164 |
| Gemma 4 26B 3x slower | 282, $0.957 / 282, $0.964 | 265, $0.0034 / 265, $0.0034 | 275, $0.577, 5.63 s / 276, $0.433, 7.16 s | 286 | 276, $0.393 | 284, $1.164 |
| Free endpoints fail half the time | 280, $0.964 / 280, $0.964 | 137, $0.0034 / 137, $0.0034 | 276, $0.433, 3.84 s / 276, $0.433, 3.84 s | 286 | 276, $0.393 | 284, $1.164 |
| Same outage, reliability weighted | 282, $0.966 / 280, $0.964 | 268, $0.028 / 165, $0.018 | 276, $0.433, 3.84 s / 276, $0.433, 3.84 s | 286 | 276, $0.393 | 284, $1.164 |
| Gemini 4 Argon fails 30% of calls | 265, $0.024 / 232, $0.609 | 265, $0.018 / 265, $0.018 | 268, $0.035, 2.03 s / 251, $0.325, 2.85 s | 285 | 261, $0.233 | 203, $0.729 |

**Original test split (120 prompts).**

| Scenario | Best quality: told / old estimates | Lowest cost: told / old estimates | Fastest: told / old estimates | Oracle (best quality) | Rule router | Always strongest |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Observed drift (Nov 12-13) | 112, $0.421 / 112, $0.421 | 102, $0.0032 / 103, $0.0003 | 110, $0.226, 5.08 s / 29, $0.099, 0.13 s | 116 | 106, $0.179 | 112, $0.493 |
| Gemma 4 26B costs 30x more | 111, $0.420 / 112, $0.523 | 104, $0 / 103, $0.0097 | 102, $0.119, 2.33 s / 102, $0.116, 2.09 s | 116 | 105, $0.266 | 112, $0.493 |
| Gemini 4 Argon costs 4x more | 112, $1.667 / 112, $1.675 | 104, $0.0087 / 103, $0.0003 | 102, $0.414, 2.09 s / 102, $0.414, 2.09 s | 116 | 105, $0.694 | 112, $1.972 |
| Gemini 4 Argon costs a quarter | 111, $0.104 / 112, $0.108 | 104, $0 / 103, $0.0003 | 103, $0.042, 2.33 s / 102, $0.041, 2.09 s | 116 | 105, $0.059 | 112, $0.123 |
| Free OVHcloud endpoints 3x slower | 112, $0.415 / 112, $0.421 | 103, $0.0003 / 103, $0.0003 | 105, $0.194, 3.17 s / 102, $0.116, 2.09 s | 116 | 105, $0.186 | 112, $0.493 |
| Gemma 4 26B 3x slower | 111, $0.418 / 112, $0.421 | 103, $0.0003 / 103, $0.0003 | 102, $0.116, 2.09 s / 102, $0.116, 2.09 s | 116 | 105, $0.186 | 112, $0.493 |
| Free endpoints fail half the time | 111, $0.421 / 111, $0.421 | 48, $0.0003 / 48, $0.0003 | 102, $0.116, 2.09 s / 102, $0.116, 2.09 s | 115 | 105, $0.186 | 112, $0.493 |
| Same outage, reliability weighted | 112, $0.424 / 111, $0.421 | 103, $0.015 / 67, $0.0087 | 104, $0.119, 2.56 s / 104, $0.119, 2.56 s | 115 | 105, $0.186 | 112, $0.493 |
| Gemini 4 Argon fails 30% of calls | 105, $0.012 / 99, $0.369 | 104, $0.0087 / 104, $0.0087 | 100, $0.022, 2.46 s / 94, $0.076, 2.00 s | 114 | 97, $0.143 | 84, $0.414 |

What the scenarios show, on both sets:

- **Retirement and price changes work.** Told that Mercury 3 is retired, the fastest setting keeps 276 right instead of 83. Told that Gemma 4 26B costs 30 times more, the lowest-cost setting stops using it (267 right for $0, against 265 for $0.101 with old estimates), and best quality saves $0.20 for the same 282. Told that Gemini 4 Argon costs a quarter, best quality spends $0.24 instead of $0.25.
- **The most expensive model barely reacts to its own price.** Costs are divided by the highest expected cost among the available models, so when Gemini 4 Argon, the most expensive, costs four times more its normalized cost stays 1. Best quality keeps it (4 choices change) and pays $3.82; meanwhile every other model looks cheaper, so the lowest-cost setting sends 100 prompts to Gemma 4 26B instead of 22 and spends five times as much.
- **Time normalization has the same flaw.** Told that the three free OVHcloud models, the slowest, are three times slower, the fastest setting got *slower*: every other model's normalized time shrinks, the time penalty stops separating them, and quality wins, so 192 prompts go to Gemini 4 Argon instead of 113 (7.11 s median instead of 3.84 s, for $0.94 instead of $0.43, with 6 more right). Told that Gemma 4 26B is three times slower, it reacts as expected: 5.63 s instead of 7.16 s.
- **Reliability counts only with a weight.** The tuned priorities have a reliability weight of 0, so when the four free remote models fail half their calls, the lowest-cost setting drops to 137 right whether it is told or not. With the weight at 1, the told router moves to models that work and gets 268, against 165 with old estimates. When Gemini 4 Argon fails 30% of calls, the told best-quality router gets 265 against 232 (always using Gemini: 203).

### Priority sweep (fresh prompts)

Accuracy has weight 1; one other weight is varied with the rest at 0.

| Weight | Cost weight varied: correct, cost, median time | Latency weight varied: correct, cost, median time |
| ---: | --- | --- |
| 0 | 284, $1.164, 8.10 s | 284, $1.164, 8.10 s |
| 0.005 | 284, $1.164, 8.10 s | 284, $1.164, 8.10 s |
| 0.01 | 284, $1.164, 8.10 s | 284, $1.164, 8.10 s |
| 0.02 | 284, $1.106, 8.04 s | 284, $1.164, 8.10 s |
| 0.05 | 281, $0.938, 7.28 s | 284, $1.164, 8.10 s |
| 0.1 | 270, $0.335, 4.60 s | 284, $1.164, 8.10 s |
| 0.2 | 265, $0.018, 3.93 s | 284, $1.156, 8.09 s |
| 0.5 | 265, $0.018, 3.93 s | 282, $0.969, 7.28 s |
| 1 | 265, $0.0034, 5.74 s | 282, $0.969, 7.28 s |
| 2 | 267, $0, 6.57 s | 275, $0.384, 4.01 s |
| 5 | 267, $0, 6.57 s | 273, $0.323, 3.93 s |

Most of the saving arrives by a cost weight of 0.2 (from $1.16 to $0.018 for 19 fewer right answers), and most of the speed by a latency weight of 2 (from 8.1 s to 4.0 s for 9 fewer).

## Export and interface

**Export.** `GET /api/v1/learned/export/{table}?format=csv|json` and `python -m app.learned.export TABLE --format csv --out FILE` serve seven tables, built only from committed files:

- `strategies`: every strategy and oracle, with intervals and per-task results;
- `comparisons`: the paired tests;
- `errors`: routing errors and oracle gap per preset and task;
- `robustness`: every scenario and strategy;
- `sweep`: the priority sweep;
- `decisions`: every strategy's choice on every prompt;
- `cells`: every model's outcome on every prompt.

None of them contains model responses, request IDs, or keys.

**Interface.** The tabbed console is replaced by a public research site, written for someone who has never seen the project: no page mentions checkpoints, and every number on it is computed from the committed reports. It has light and dark themes (following the system setting, with a toggle), hash routes so every page and model can be linked, and it fits a 390 px phone screen without sideways scrolling.

- **Home:** what the router does, a diagram of which models the fresh prompts went to under each priority, four findings computed from the final report, and how it works.
- **Router:** the adaptive router with priority cards, example prompts, and custom weights under advanced settings. Before anything is sent it shows the decision, every model's score and why the others lost, and a notice that names where **Run** would send the prompt (a third-party API, or the local Ollama server) and that route's data policy. A "Stress-test this decision" panel changes one condition for one model (price, speed, failure rate, or retirement) and shows whether the choice moves, with no provider call.
- **Models:** the pool as a catalog, with search, an access filter (paid, free, local), sorting by accuracy, price, speed, or context, live availability, snapshot and live prices side by side, and accuracy. Each model has its own page with per-task accuracy, latency, and how often each priority picks it.
- **Research:** highlights; a leaderboard with 95% intervals; accuracy against cost and time, with the oracle; "Is it real?" (the paired tests); where the router goes wrong, with real examples; robustness scenarios; the priority sweep; how the router was built (tuning, the model x task matrix, the classifier comparison); method and limits; and downloads of the seven export tables.
- **FAQ:** eleven questions a visitor would ask (which model is best per task, how much routing saves, what happens when a model is retired, whether a prompt is stored), each answered from the data.
- **Lab:** the earlier tools, presented as baselines: the rule-based router, side-by-side comparison, the context filter, and the GSM8K pilot runs.

New API endpoints:

- `GET /learned/final`;
- `GET /learned/pool`;
- `GET /learned/catalog` and `POST /learned/catalog/refresh`;
- `POST /learned/what-if`;
- `GET /learned/export/{table}`.

## Tests

Backend tests went from 75 to 100, all offline: provider catalogs and calls are served by mock transports, and a test fixture turns the startup catalog check off.

- `test_live_catalog.py`: retirement, price changes, lost hosts, the snapshot fallback, a stopped Ollama server, the router's exclusion and repricing, the API, and the Checkpoint 2 drift message.
- `test_final_eval.py`:
  - the final set: size, balance, no overlap with the suite or Checkpoint 1, and its checksum;
  - the statistics: McNemar, Holm, and reproducible intervals;
  - the fast replay matching the live router;
  - scenario transforms with nested failures;
  - the error analysis.
- `test_learned_api.py`: the final report, every export table in both formats (and that no response text appears), the pool, the what-if, and the empty states.

Frontend: 10 unit tests cover the home page and its findings, the routing preview with its third-party notice and the stress test, the model catalog and a model page, the research page and its task filters, the FAQ, the lab (rule router without a key, and a paid pilot that starts only after the estimate is confirmed), and the theme toggle. 2 Playwright tests run the site in Chrome with the API stubbed as a fresh install (no key, no reports): the home page and the router's missing-key notice, and the home page at phone width without sideways scrolling.

## Left for the week of November 26

The proposal's last week: final robustness runs and plots, finishing export and data validation, and starting the final report. From this week's results, the open points are:

- **Robustness plots:** the scenarios above as figures (accuracy and cost per scenario, told against old estimates), next to the held-out figures.
- **Data validation:** a script that checks every committed table against the raw runs and the published hashes, and a short data dictionary for the seven export tables.
- **Two design fixes, to report rather than evaluate:** score cost and time against fixed reference values (for example the snapshot's own maximum) instead of the current maximum, and give reliability a small default weight. Both change the router, so they cannot be tested on the fresh prompts without spending them; the report should describe them as recommendations, backed by the scenarios above.
- **The final report:** the method, the two evaluations, the error analysis, the robustness results, and the limits (benchmarks are not real traffic, prompt features add little here, and the router only knows the models it was measured on).
