# Week of November 19: final evaluation, error analysis, robustness, export, flagship models

This records the proposal's work-plan items for the week of November 19. The week of November 26 (final robustness runs and plots, finished export and data validation, the final report) is not started; see [what is left](#left-for-the-week-of-november-26).

| Proposal item | Status |
| --- | --- |
| Complete the held-out evaluation | Done: the frozen router on the Checkpoint 3 test split (with intervals added) and on 300 fresh prompts answered on 2026-11-13 and 14 ([details](#the-final-held-out-set), [results](#results)) |
| Finish the oracle and under-routing/over-routing analysis | Done: per priority and task, with a stricter "dominated" count, the extra cost, regret, and worked examples ([details](#oracle-gap-and-routing-errors)) |
| Implement robustness tests for changed price, latency, reliability, and user priorities | Done: a replay engine with 9 scenarios per evaluation and a priority sweep, plus a stress test on the Router page ([method](#robustness-tests), [results](#robustness-results)) |
| Begin experiment export and final interface cleanup | Done for this week: seven tables as CSV or JSON from the site and the CLI; the console rebuilt as a public research site, then redesigned on 2026-11-14 ([details](#export-and-interface)) |
| Flagship models (owner request, 2026-11-14) | Done: GPT-6.1 Sol, Gemini 4 Carbon, and Kimi K3.1 Pro on all 900 prompts (Grok 4.7 stopped over budget), a second router fit with the same recipe, and a comparison with the frozen one ([details](#flagship-models-2026-11-14)) |
| Owner decisions on 2026-11-13 and 14 | Check the live catalog; keep the Checkpoint 2 rule router (now in the Lab, as a baseline); retry the two keyed models once (still failing, so excluded); draw a fresh final set; redesign the site; add flagship models within $25 |

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
9. **Flagships make the router faster, not more accurate, on these benchmarks.** GPT-6.1 Sol is as accurate as Gemini 4 Argon (284 of 300) for $0.50 instead of $1.16, at 2.6 s instead of 8.1 s. With the three flagships in the pool, a second router fit with the same recipe:
   - **Fastest:** gets 284 right instead of 276, 1.3 s quicker at the median;
   - **Balanced:** gets 283 instead of 276;
   - **Best quality:** gets 283 instead of 282.

   None of these accuracy differences is significant after the Holm correction (p = 0.23, 0.33, 1.00). Gemini 4 Carbon and Kimi K3.1 Pro are never chosen. Grok 4.7 was stopped because its reasoning ran far past the token limit and the budget ([details](#flagship-models-2026-11-14)).

## Owner decisions (2026-11-13 and 14)

1. **Final evaluation set:** draw about 300 fresh prompts nobody has used, run the models still available on them, and evaluate the frozen router under real provider drift. More models could be added if needed; none were (see [the two keyed models](#the-two-keyed-models-retried-once)).
2. **Provider drift:** check the live catalog at startup. A retired model becomes unavailable (a failed hard requirement, with the reason shown), changed prices update expected costs, and the app falls back to the dated snapshot when the check fails.
3. **Checkpoint 2 tab:** keep it as history, and make its refusal message explain what changed. It now lives on the site's Lab page, presented as the rule-based baseline.
4. **Keyed models:** retry Gemma 4 31B and DeepSeek V4.1 Flash once; add them only if healthy.
5. **Site (2026-11-14):**
   - redesign it in the style of data-first model leaderboards;
   - use open-source components where possible;
   - no purple or generic gradient look.
6. **Flagships (2026-11-14):**
   - add GPT-6.1 Sol, Gemini 4 Carbon, Grok 4.7, and Kimi K3.1 Pro, within $25 (the account's remaining credit);
   - run them on all 900 prompts;
   - fit a second router with the same recipe;
   - report it next to the frozen one.

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

## Flagship models (2026-11-14)

The owner asked for flagship models in the pool. Four were chosen from the live OpenRouter catalog on 2026-11-14:

- GPT-6.1 Sol;
- Gemini 4 Carbon;
- Grok 4.7;
- Kimi K3.1 Pro.

The owner set three rules:

- a $25 cap, which was the account's remaining credit;
- every one of the 900 prompts, the 600-prompt suite and the 300 fresh prompts;
- a second router fit with the same recipe, reported next to the frozen one.

Pricier flagships, including GPT-6 Astra, were offered and not chosen. Command: `python -m app.learned.flagship_study --from-runs`. Report: `data/learned/flagship-study.json`. The second router is `data/learned/flagship-router-model.json`.

### Runs

The flagships are in a separate dated registry, `data/registry/flagship-pool-2026-11-14.json`. Each model is pinned to its maker's own standard tier with no fallback, and the frozen pool and its numbers are untouched.

The runner gained two options:

- `--pool flagship` selects that registry;
- `--spend-cap` takes a cap of at most $25.

A smoke test of 8 prompts per model cost $0.20 and confirmed the billed prices. Prompts, token limits (2,048 for math, 4,096 otherwise), temperature, retry policy and grading are the same as for the Checkpoint 3 pool, and code is scored by the same EvalPlus container.

| Model | Maker's host (pinned) | Price in / out per M | Prompts scored | Billed |
| --- | --- | --- | ---: | ---: |
| GPT-6.1 Sol | openai | $2 / $10 | 900 | $1.45 |
| Gemini 4 Carbon | google-ai-studio | $2 / $10 | 900 | $6.59 |
| Kimi K3.1 Pro | moonshotai/mxfp4 | $2 / $10 | 900 | $6.78 |
| Grok 4.7 (stopped) | xai | $2 / $6 | 375 | $3.33 |

**Grok 4.7 was stopped.** On knowledge questions its reasoning ignored the 4,096-token answer limit: one answer used 35,234 tokens and ten minutes, and its knowledge answers averaged $0.025 each, about six times what Gemini 4 Argon's token counts had predicted. Finishing would have taken the total to about $28, and the per-run caps would have stopped every model partway. Both runs were stopped and resumed without Grok; the runner resumes where it left off. Grok had answered 375 prompts:

- math: 190 of 200 on the suite and 96 of 100 on the fresh prompts;
- knowledge: 18 of 21 and 51 of 54.

Those answers are kept in `data/learned/flagship-cells.jsonl`. A model needs a scored answer to every prompt to join the pool, so Grok is reported as excluded, with its reason and cost.

Spend for the flagships:

- **Recorded:** $18.34 in all ($11.52 suite, $6.63 fresh, $0.20 smoke).
- **Billed:** the key's usage for the day rose by $18.46. The $0.12 difference is calls that were in flight when the first runs were stopped.

### The second router

The Checkpoint 3 recipe is used unchanged on all 12 models (9 + 3), with `train.py`'s own functions:

- **Classifier:** logistic regression was chosen over gradient-boosted trees on validation log loss (0.433 against 0.451, C = 0.003).
- **Presets:** tuned on the validation split with the same grids and accuracy floors.
- **Refit:** on train + validation, giving 5,760 prompt-model pairs and 71 features.

As before, the per-task table predicts better on validation (log loss 0.425).

| Priority | Cost weight | Time weight | Reliability weight | Validation |
| --- | ---: | ---: | ---: | --- |
| Lowest cost | 1.0 | 0.05 | 0.5 | 101/120, $0.0082 |
| Best quality | 0.05 | 0.05 | 0.0 | 110/120, $0.48 |
| Fastest | 0.05 | 1.0 | 0.0 | 106/120, $0.10 |
| Balanced | 0.3 | 0.5 | 0.0 | 106/120, $0.10 |

**Strongest flagship.** The baseline "always the strongest flagship" uses Gemini 4 Carbon. It was chosen by a rule fixed before the test and fresh results were read: the most right answers on the train and validation prompts.

**Checks.**

- **Pre-registered questions:** six paired questions were fixed in code before the flagships' results were read.
- **Frozen router unchanged:** the frozen router's choices in this study must reproduce its published final evaluation exactly; the study stops if they do not.
- **Reproducible:** a rebuild from the committed cell tables, without the raw runs, is byte for byte the same.

The fresh prompts had already been used once, to evaluate the frozen router. Nothing here was chosen on them; this reads them a second time.

### The models on the fresh prompts

Flagships are in bold. Mercury 3 (retired) is left out.

| Model | Right | Math | Knowledge | Code | Billed | Median time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **GPT-6.1 Sol** | 284/300 | 97/100 | 92/100 | 95/100 | $0.50 | 2.6 s |
| Gemini 4 Argon | 284/300 | 98/100 | 92/100 | 94/100 | $1.16 | 8.1 s |
| **Gemini 4 Carbon** | 284/300 | 97/100 | 91/100 | 96/100 | $2.16 | 11.4 s |
| **Kimi K3.1 Pro** | 278/300 | 97/100 | 85/100 | 96/100 | $2.33 | 12.6 s |
| Gemma 4 26B A4B | 268/300 | 96/100 | 83/100 | 89/100 | $0.04 | 2.0 s |
| Nemotron 3 Ultra 550B (free) | 266/300 | 95/100 | 85/100 | 86/100 | $0 | 7.4 s |
| DeepSeek V4 Flash | 262/300 | 95/100 | 79/100 | 88/100 | $0.07 | 2.9 s |
| gpt-oss-120b | 259/300 | 96/100 | 82/100 | 81/100 | $0 | 3.8 s |
| Qwen 3.8 27B | 253/300 | 96/100 | 73/100 | 84/100 | $0 | 6.5 s |
| Llama 3.3 70B Instruct | 247/300 | 95/100 | 76/100 | 76/100 | $0 | 10.5 s |
| Qwen 3.5 9B (local) | 242/300 | 96/100 | 75/100 | 71/100 | $0 | 6.9 s |

### Fresh prompts (300)

| Strategy | Right | Billed | Median time | To flagships |
| --- | ---: | ---: | ---: | ---: |
| With flagships, best quality | 283/300 (92-97%) | $1.03 | 7.1 s | 34% |
| With flagships, lowest cost | 265/300 (85-92%) | $0.02 | 4.1 s | 0% |
| With flagships, fastest | 284/300 (92-97%) | $0.50 | 2.6 s | 100% |
| With flagships, balanced | 283/300 (92-97%) | $0.40 | 2.2 s | 64% |
| Frozen router, best quality | 282/300 (91-97%) | $0.96 | 7.2 s | 0% |
| Frozen router, lowest cost | 265/300 (85-92%) | $0.0034 | 5.7 s | 0% |
| Frozen router, fastest | 276/300 (89-95%) | $0.43 | 3.8 s | 0% |
| Frozen router, balanced | 276/300 (89-95%) | $0.43 | 3.8 s | 0% |
| Always Gemini 4 Carbon | 284/300 (92-97%) | $2.16 | 11.5 s | 100% |
| Always Gemini 4 Argon | 284/300 (92-97%) | $1.16 | 8.1 s | 0% |
| Always Gemma 4 26B A4B | 268/300 (86-93%) | $0.04 | 2.0 s | 0% |
| Per-task averages, best quality | 283/300 (92-97%) | $1.06 | 7.3 s | 33% |
| Hindsight oracle, best quality | 289/300 (94-98%) | $0.09 | 1.8 s | 3% |
| Hindsight oracle, lowest cost | 289/300 (94-98%) | $0.06 | 2.7 s | 2% |

| Question | Difference (95% CI) | Holm p | Cost ratio (95% CI) |
| --- | --- | ---: | --- |
| Does the best-quality setting get more right with the flagships in the pool? | +0.3 points (+0.0 to +1.0) | 1.00 | 1.07 (1.03 to 1.10) |
| Is the best-quality setting as accurate as always using the strongest flagship, for less? | -0.3 points (-1.7 to +0.7) | 1.00 | 0.48 (0.43 to 0.52) |
| Does adding the flagships change the lowest-cost setting? | +0.0 points (-1.7 to +2.0) | 1.00 | 5.23 (3.62 to 8.64) |
| Does adding the flagships change the fastest setting? | +2.7 points (+0.7 to +5.0) | 0.23 | 1.15 (0.97 to 1.41) |
| Does the balanced setting do better with the flagships in the pool? | +2.3 points (+0.3 to +4.7) | 0.33 | 0.91 (0.75 to 1.13) |
| With the flagships, do the prompt features add accuracy beyond per-task averages? | +0.0 points (+0.0 to +0.0) | 1.00 | 0.97 (0.94 to 0.99) |

Time differences, as medians with 95% intervals:

- **Fastest:** the flagship version is 1.3 s quicker than the frozen fastest setting (0.6 to 1.9 s).
- **Balanced:** 1.7 s quicker (1.1 to 2.3 s).
- **Best quality:** no clear difference.

### Original test split (120)

| Strategy | Right | Billed | Median time | To flagships |
| --- | ---: | ---: | ---: | ---: |
| With flagships, best quality | 111/120 (88-97%) | $0.45 | 4.6 s | 32% |
| With flagships, lowest cost | 105/120 (82-93%) | $0.0087 | 8.6 s | 0% |
| With flagships, fastest | 104/120 (81-92%) | $0.12 | 2.0 s | 43% |
| With flagships, balanced | 103/120 (79-92%) | $0.11 | 2.0 s | 38% |
| Frozen router, best quality | 112/120 (88-98%) | $0.42 | 5.4 s | 0% |
| Frozen router, lowest cost | 103/120 (79-92%) | $0.0003 | 12.7 s | 0% |
| Frozen router, fastest | 102/120 (78-91%) | $0.12 | 2.1 s | 0% |
| Frozen router, balanced | 102/120 (78-91%) | $0.12 | 2.1 s | 0% |
| Always Gemini 4 Carbon | 110/120 (87-96%) | $0.91 | 11.7 s | 100% |
| Always Gemini 4 Argon | 112/120 (88-98%) | $0.49 | 5.1 s | 0% |
| Always Gemma 4 26B A4B | 103/120 (79-92%) | $0.02 | 5.1 s | 0% |
| Per-task averages, best quality | 111/120 (88-97%) | $0.46 | 4.9 s | 33% |
| Hindsight oracle, best quality | 116/120 (93-99%) | $0.03 | 1.9 s | 2% |
| Hindsight oracle, lowest cost | 116/120 (93-99%) | $0.01 | 5.4 s | 0% |

| Question | Difference (95% CI) | Holm p | Cost ratio (95% CI) |
| --- | --- | ---: | --- |
| Does the best-quality setting get more right with the flagships in the pool? | -0.8 points (-2.5 to +0.0) | 1.00 | 1.06 (1.02 to 1.12) |
| Is the best-quality setting as accurate as always using the strongest flagship, for less? | +0.8 points (-2.5 to +4.2) | 1.00 | 0.50 (0.44 to 0.55) |
| Does adding the flagships change the lowest-cost setting? | +1.7 points (-2.5 to +6.7) | 1.00 | 26.86 (9.75 to 67.20) |
| Does adding the flagships change the fastest setting? | +1.7 points (-1.7 to +5.0) | 1.00 | 1.02 (0.79 to 1.35) |
| Does the balanced setting do better with the flagships in the pool? | +0.8 points (-1.7 to +3.3) | 1.00 | 0.93 (0.72 to 1.21) |
| With the flagships, do the prompt features add accuracy beyond per-task averages? | +0.0 points (+0.0 to +0.0) | 1.00 | 0.97 (0.93 to 0.99) |

On this split the Fastest and Balanced settings of both routers still used Mercury 3, which was served in late October.

### What it shows

1. **The flagships do not make the best-quality setting more accurate here.** It got 283 of 300 against 282 without them, for 7% more money. GPT-6.1 Sol, Gemini 4 Argon and Gemini 4 Carbon each got 284, so these four benchmarks are at the ceiling for strong models. Hindsight over all 12 models reaches 289 instead of 286: three prompts only a flagship got right.
2. **GPT-6.1 Sol is the useful addition.** It is as accurate as Gemini 4 Argon (284 of 300) for $0.50 instead of $1.16, at a 2.6 s median instead of 8.1 s.
   - **Fastest:** sends 299 of 300 prompts to it and gets 284 right instead of the frozen router's 276, 1.3 s quicker.
   - **Balanced:** splits between it and Gemma 4 26B and gets 283.
   - **Significance:** both accuracy intervals exclude zero (+2.7 and +2.3 points), but with six questions the Holm-adjusted McNemar p-values are 0.23 and 0.33, so they are not counted as significant.
3. **The expensive flagships are never chosen.**
   - **Gemini 4 Carbon** costs 1.9 times as much as Gemini 4 Argon for the same 284.
   - **Kimi K3.1 Pro** got 278 for $2.33 and is the slowest, at 12.6 s.
   - **No setting picks either one.** Always using Gemini 4 Carbon costs $2.16; the best-quality setting matches it within 0.3 points for 48% of that.
4. **The lowest-cost setting got dearer, not better.** It got 265 again, but for $0.018 instead of $0.0034. The new validation tuning gave it a reliability weight of 0.5, so it sends 100 prompts to Gemma 4 26B instead of 22 and 100 to the free Nemotron 3 Ultra instead of 178. That is a tuning change on 120 validation prompts, not an effect of the flagships, which it never uses.
5. **Prompt features still add nothing measurable.** Per-task averages tie the second router at best quality (283 against 283).
6. **On the original split nothing changes measurably.** No difference is significant, and best quality got 111 against 112.

**On the site.**

- **Charts and leaderboard:** the Models page, the Home charts and the Research page include the three flagships.
- **Research section:** "With flagship models" shows the tables above, the questions, and the excluded model.
- **Router page:** a switch routes over the pool with the flagships using the second router. The live catalog check now covers the flagships too.

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

**Interface.** The tabbed console was first replaced by a public research site, then redesigned on 2026-11-14 in the style of data-first model leaderboards. It is written for someone who has never seen the project: no page mentions checkpoints, and every number on it is computed from the committed reports.

- **Look:**
  - white pages with a gray band for the summary;
  - a serif display face (Source Serif 4) for titles, Inter for text and numbers, and hairline cards;
  - color only for data: each model maker has one hue, and every bar carries the maker's logo and the model's name, so color is never the only label;
  - the adaptive router drawn as hatched black bars and black diamonds;
  - no gradients and no accent color;
  - a selected dark theme (its own steps, not an inversion), following the system setting with a toggle.

  Every page fits a 390 px phone screen without sideways scrolling; the one wide chart scrolls inside its card.
- **Open-source parts:**
  - Recharts 3.10.1 (MIT) for the bar charts;
  - the LobeHub icon set (MIT) for the maker logos (`frontend/src/assets/makers`, with its license);
  - Inter and Source Serif 4 from Fontsource (SIL Open Font License);
  - the existing Radix primitives and Lucide icons.

  The trade-off scatter and the share bars are small SVG components of our own.
- **Home:**
  - the question and two actions;
  - highlight cards that name the most accurate, fastest, and cheapest models, the router's two headline results, and the flagship result;
  - bar charts of right answers, billed cost, and median time for every model, with the routers among them;
  - accuracy against cost on a log scale, with free models at the left and a dotted line through the cheapest model at each accuracy;
  - where each priority sends the fresh prompts;
  - how the router works.
- **Router:**
  - opens with a scored decision for the example prompt (a preview never calls a provider);
  - a switch between the standard pool and the pool with the flagships;
  - the decision, with the notice naming where **Run** would send the prompt;
  - every model's score, and the stress test.
- **Models:** a sortable leaderboard table:
  - accuracy overall and per task on the fresh prompts;
  - input and output prices, with live prices highlighted;
  - billed cost for all fresh prompts, median time, context, and status;
  - filters for paid, free, local, and flagship models.

  Each model has its own page with per-task accuracy on both prompt sets, how often each priority picks it, its price and availability, and its data policy.
- **Research:**
  - a sticky table of contents;
  - the highlights and the leaderboard with 95% intervals;
  - accuracy against cost and time;
  - the paired tests;
  - the flagship study;
  - routing errors with examples;
  - robustness, the priority sweep, and how the router was built;
  - method and limits, and the downloads.
- **FAQ:** twelve questions answered from the data, including whether flagship models help.
- **Lab:** the earlier tools, presented as baselines.

New API endpoints:

- `GET /learned/final`;
- `GET /learned/pool`;
- `GET /learned/catalog` and `POST /learned/catalog/refresh`;
- `POST /learned/what-if`;
- `GET /learned/export/{table}`;
- `GET /learned/flagships` (the flagship study), and a `pool` field on route, preview, and what-if requests that selects the second router.

## Tests

Backend tests went from 75 to 108, all offline: provider catalogs and calls are served by mock transports, and a test fixture turns the startup catalog check off.

- `test_live_catalog.py`: retirement, price changes, lost hosts, the snapshot fallback, a stopped Ollama server, the router's exclusion and repricing, the API, and the Checkpoint 2 drift message.
- `test_final_eval.py`:
  - the final set: size, balance, no overlap with the suite or Checkpoint 1, and its checksum;
  - the statistics: McNemar, Holm, and reproducible intervals;
  - the fast replay matching the live router;
  - scenario transforms with nested failures;
  - the error analysis.
- `test_learned_api.py`: the final report, every export table in both formats (and that no response text appears), the pool, the what-if, and the empty states.
- `test_flagship_study.py`:
  - the flagship registry (paid, checksummed, one pinned host each) and the combined pool;
  - the strongest-flagship rule, which uses only train and validation and breaks ties by cost;
  - the runner refusing a cap above $25;
  - requests routing over the pool they name, with the stopped model never routed;
  - a broken flagship router file leaving the standard router running.

Frontend: 11 unit tests cover the home page and its findings, the flagship study on the research, models, and router pages, the routing preview with its third-party notice and the stress test, the model catalog and a model page, the research page and its task filters, the FAQ, the lab (rule router without a key, and a paid pilot that starts only after the estimate is confirmed), and the theme toggle. 2 Playwright tests run the site in Chrome with the API stubbed as a fresh install (no key, no reports): the home page and the router's missing-key notice, and the home page at phone width without sideways scrolling.

## Week of November 26: robustness figures, data validation, failure handling, more models, interface

This records the proposal's work-plan items for the week of November 26, done on 2026-11-20 and 21. The final report is left for the week of December 3, as the owner asked.

| Proposal item (week of Nov 26) | Status |
| --- | --- |
| Run the robustness experiments and verify final plots | Done: the scenarios and the priority sweep rebuilt from committed data, with new figures and interactive charts on the site ([details](#robustness-figures)) |
| Finish experiment export, data validation, and failure handling | Done: four new export tables, an offline validation command that runs in CI, a data dictionary, a one-step fallback for live calls, and a spend cap that spans related runs ([details](#export-validation-and-failure-handling)) |
| Fix remaining interface and backend bugs | Done: the reviewer's open points, the Lab restyle, and a check of every page in both themes and at phone width ([details](#interface)) |
| Begin the final report and organize final results | Results organized (pool studies, figures, data dictionary); writing the report itself is left for the week of December 3 |
| Owner request (2026-11-20): more models and more interface work | Five more models on all 900 prompts and a third router fit on every model ([details](#more-models-the-wide-study)); a search palette, a comparison page, and interactive charts ([details](#interface)) |

### Results in brief

- **Best budget model:** GPT-6 Luna got 274 of the 300 fresh prompts right for $0.047. Gemma 4 26B, the cheapest paid model before, got 268 for $0.035.
- **A router fit on all 16 models:**
  - at lowest cost, 270 right for $0.022, against 265 for $0.0034 for the frozen router;
  - at best quality, 282, the same as the frozen router;
  - at fastest and balanced, 278 right for $0.26 at 2.3 s; the frozen router got 276 for $0.43 at 3.8 s, and the flagship router 284 for $0.50 at 2.6 s.
- **Significance:** none of the eight fixed comparisons is significant after the Holm correction, on the fresh prompts or the test split. More models moved where the settings land, and none of the changes can be told from chance.
- **Spend:** $1.00 billed for the five budget models on 900 prompts. $1.80 of credit is left for the demonstration.

### More models: the wide study

**Budget.** The OpenRouter account had $2.82 of credit left on 2026-11-20, against $9.48 on 2026-11-14 (this project's key had not been used since). Only very cheap paid models and free ones were added, and about $1.50 was kept for the live demonstration. The runner's cap was set at $0.80 for the suite and $0.45 for the fresh prompts.

**Selection.** Seven candidates from the live catalog were smoke-tested on 8 prompts each ($0.015):

- **Paid, chosen:** GPT-6 Luna (OpenAI, $0.10 / $0.50 per million tokens), MiMo-V2.6 Flash (Xiaomi, $0.14 / $0.28), Muse Ember (Meta, $0.10 / $0.50), and Ministral 8B (Mistral, $0.15 / $0.15). Each is pinned to its maker's own host.
- **Free, chosen:** ERNIE 5.5 Flash (Baidu, free preview).
- **Dropped:** GLM-5.3 Flash, which projected $0.58 for a 20-second median response the router would almost never pick, and Nemotron 3.5 Lightning (free), because the account's 1,000 free requests a day covered one free model, and NVIDIA is already in the pool. The registry keeps Nemotron 3.5 Lightning, so the study reports it as excluded with this reason.

Registry: `data/registry/budget-pool-2026-11-20.json`. Prompts, token limits, retry policy, and grading are unchanged.

**Runs (2026-11-21).** The four paid models ran on the 600 suite prompts ($0.67 billed) and the 300 fresh prompts ($0.33). Code was scored by the EvalPlus tests in Docker, as before.

| Model | Suite (600) | Fresh (300) | Failed calls (suite, fresh) | Billed, both sets | Median time, fresh |
| --- | --- | --- | --- | --- | --- |
| GPT-6 Luna | 529 | 274 | 1, 0 | $0.132 | 2.7 s |
| MiMo-V2.6 Flash | 511 | 262 | 25, 13 | $0.181 | 8.2 s |
| Muse Ember | 495 | 266 | 47, 19 | $0.601 | 2.0 s |
| Ministral 8B | 472 | 232 | 0, 0 | $0.088 | 3.1 s |
| ERNIE 5.5 Flash (free) | 507 | 242 of 284 | 38, 27 | $0 | 2.1 s |

A failed call is an unparseable or empty answer after the retry, or a rate-limited free call. Each counts as wrong.

**ERNIE 5.5 Flash is excluded.**

- **What happened:** the runner keeps free requests under 950 a day, below the account's 1,000. ERNIE made 961 requests on 2026-11-21 (UTC), counting retries and the smoke test, so the runner stopped it 16 fresh prompts short.
- **The rule:** the rule set for Grok 4.7 applies. Only a model that answered every prompt joins the pool; the rest are reported with how far they got.
- **The commitment:** the reason was written into `studies.py` before the wide study was first built, with a commitment. If the 16 prompts are run after the quota resets, the study is rebuilt with ERNIE, whatever the result.

**Pool studies.** The flagship study is now one of two pool studies (`app/learned/studies.py`, `app/learned/pool_study.py`). A study adds one or more dated registries to the frozen pool, refits the Checkpoint 3 recipe unchanged, and evaluates the new router next to the frozen one and any earlier study's router.

- **Flagship study:** regenerated by the general code with identical numbers and a byte-identical router. Only the report's field names and one strategy ID changed (`fixed_top_flagship` is now `fixed_top_added`).
- **Wide study:** the frozen pool plus the flagships and the budget models. Its eight questions were fixed in code on 2026-11-21, while the budget models were still running. They compare the wide router with the frozen router at each priority, with the flagship router at best quality and lowest cost, with always using the strongest added model, and with per-task averages.
- **Checks:** the study stops unless the frozen router's choices reproduce `final-evaluation.json` and the flagship router's choices reproduce `flagship-study.json`, on both prompt sets.

Command: `python -m app.learned.pool_study --study wide --from-runs`. Report: `data/learned/wide-study.json`; router: `data/learned/wide-router-model.json`.

**Wide study results on the 300 fresh prompts.** The study router was fit on 7,680 (prompt, model) rows from the suite's training split. Logistic regression was selected again (C = 0.003).

| Setting | Wide router | Frozen router | Flagship router |
| --- | --- | --- | --- |
| Best quality | 282 · $0.97 · 7.8 s | 282 · $0.96 · 7.2 s | 283 · $1.03 · 7.1 s |
| Lowest cost | 270 · $0.022 · 3.2 s | 265 · $0.0034 · 5.7 s | 265 · $0.018 · 4.1 s |
| Fastest | 278 · $0.26 · 2.3 s | 276 · $0.43 · 3.8 s | 284 · $0.50 · 2.6 s |
| Balanced | 278 · $0.26 · 2.3 s | 276 · $0.43 · 3.8 s | 283 · $0.40 · 2.2 s |

Each cell gives right answers, billed cost for all 300 prompts, and median time.

- **Where the prompts went:**
  - at lowest cost, 110 went to GPT-6 Luna (mostly knowledge questions) and the rest to the free gpt-oss-120b and Nemotron 3 Ultra;
  - at best quality, MiMo-V2.6 Flash took 98 math prompts;
  - at fastest, Muse Ember took the math prompts, GPT-6 Luna most knowledge questions, and GPT-6.1 Sol the code.
- **The fixed questions:** none is significant; every adjusted p is 1.00. The largest raw difference is lowest cost against the frozen router: 5 more right (95% interval 2 fewer to 12 more), p = 0.27 before adjustment.
- **Fastest against the flagship router** (a descriptive comparison, not one of the fixed questions): 6 fewer right, for $0.24 less and 0.3 s quicker. The loss is on knowledge questions, 87 right against 92, where it used GPT-6 Luna instead of GPT-6.1 Sol.
- **Per-task reference:** it again matches the router at best quality, 282 against 282.
- **Hindsight oracle:** 291 of 300, up from 289 with the flagships, so the extra models add room the router does not use.
- **Original test split (120 prompts):** the same picture; no difference is larger than 4 right, and none is significant.

### Robustness figures

`python -m app.learned.plots` now also draws, from the committed report, three figures for the fresh prompts (light into `docs/figures/`, dark with `--slides`):

- `final-robustness`: right answers for each scenario, comparing the router told about the change with the same router using old estimates;
- `final-robustness-cost`: the same comparison for billed cost, on a log scale;
- `final-priority-sweep`: accuracy against billed cost as the cost weight rises, and against median time as the latency weight rises.

The site shows the same data as interactive charts on the Research page.

### Export, validation, and failure handling

- **Export:** four more tables, served from the site and `python -m app.learned.export`:
  - `study_strategies`;
  - `study_comparisons`;
  - `study_models`;
  - `added_cells`.

  The seven original tables are byte-identical.
- **Data dictionary:** `docs/data-dictionary.md` gives every column's meaning and unit, for every committed data file and export table.
- **Validation:** `python -m app.learned.validate` checks, offline:
  - the checksums of every cell table, suite, router file, and the fresh set;
  - row counts, unique cells, and known prompts;
  - that no response text is stored;
  - every report's model matrix, recomputed from the cells;
  - that no file holds anything that looks like a key.

  It runs in CI after the tests.
- **Failure handling:** if the model a live run chose still fails after its one retry, the next-best eligible model answers instead, once, and the page says so. Previously the call simply failed.
- **Spend cap:** the runner's `--count-spend-from` makes one cap cover related runs (suite, fresh set, smoke). This was the reviewer's open point from 2026-11-14.

### Interface

- **Search palette:** Ctrl+K (or ⌘K) on any page searches the pages, models, research sections, and FAQ answers, and opens the one picked with the keyboard.
- **Comparing models:** the Models table has maker filter chips, a CSV download, and check boxes for up to four models. They open a side-by-side page (`#/compare?models=…`) with accuracy per task, cost, time, and how often the router chose each model. Every model page has a Compare button.
- **Home:** an accuracy explorer plots every model, and the router's four settings, against cost or time, for the frozen pool or a study's pool.
- **Router:**
  - the pool switch offers the frozen pool, the pool with the flagships, and every model;
  - each candidate's score is a bar split into its accuracy, cost, time, and reliability terms;
  - a notice says when the chosen model failed and the next one answered (see failure handling).
- **Research:**
  - a robustness explorer: each scenario as a pair of marks, the router told about the change and the router with old estimates, per priority, as right answers or billed cost;
  - a priority explorer: a slider and a clickable path showing right answers, cost, time, and where the prompts went at each weight;
  - one section per pool study, and downloads for all eleven tables.
- **Prompt explorer (`#/prompts`):**
  - every prompt of the fresh set or the test split, with each model's outcome as a strip of marks and the frozen router's pick under the chosen priority;
  - filters for task, benchmark, and text, and quick filters such as "Router wrong, another model right" (4 fresh prompts at best quality) and "No model right" (9);
  - each prompt opens at `#/prompts/<id>`, with its full text, the expected answer, the router's pick under each priority, and every model's result, time, and cost.

  It is served by `GET /api/v1/learned/prompts`. Responses are now gzip-compressed: the fresh set's 767 KB goes over the wire as 84 KB.
- **Lab:** the earlier rule-based tools, restyled in the site's design.
- **Fixes:** the Kimi logo was invisible in dark mode; wide charts widened the page at phone width; three new makers (Xiaomi, Mistral, Baidu) got logos and colors.
- **Checked:** every page in light and dark at 1,440 and 390 pixels wide, with no sideways scrolling.

### Tests

- **Backend:** 123 tests pass (`python -m pytest backend/tests`); ruff and mypy are clean. New this week:
  - `test_pool_study.py` (was `test_flagship_study.py`): the strongest added model, combining pools, one spend cap across related runs, serving a study's router, and the studies API;
  - `test_api.py`: a live route falls back once when the chosen model keeps failing;
  - `test_validate.py`: a changed cell, response text, repeated cells, unknown prompts, and a study's cell tables each fail the validator;
  - `test_plots.py`: the new figures are drawn;
  - `test_explorer.py`: the prompt explorer joins every prompt with every model and choice, skips a missing table, and rejects a missing or unknown prompt set.
- **Validation:** 29 checks pass; CI runs them after the tests.
- **Frontend:** 22 tests pass, covering the search palette, the comparison page, the explorers, and the prompt explorer. TypeScript, ESLint, and the production build are clean.
- **End to end:** the 2 Playwright tests pass in Chrome.
- **Data:** the flagship and wide studies rebuild byte for byte from committed files.

## Left for the week of December 3

- **The final report:**
  - the method;
  - the two evaluations;
  - the error analysis;
  - the robustness results;
  - the pool studies: a fast, accurate flagship helps the faster settings, the expensive flagships are never chosen, and cheap models add small gains at the lowest-cost setting but none that is significant;
  - the limits: benchmarks are not real traffic, they are at the ceiling for strong models, prompt features add little here, and the router only knows the models it was measured on.
- **Two design fixes, to report rather than evaluate:** score cost and time against fixed reference values (for example the snapshot's own maximum) instead of the current maximum, and give reliability a small default weight. Both change the router, so they cannot be tested on the fresh prompts without spending them; the report should describe them as recommendations, backed by the scenarios above.
- **Optional:** run ERNIE 5.5 Flash's 16 unsent fresh prompts after the free quota resets, and rebuild the wide study with it (`--study wide --from-runs`).
- **The final presentation and live demonstration**, rehearsed with the [live demo guide](live-demo-guide.md).
