# Checkpoint 2 presentation script

This script follows `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx` (9 slides, in the format of the original Checkpoint 2 deck). It runs about seven minutes plus the live demo, which happens after slide 8. Each slide's speaker notes hold a shorter version of the same text.

## The simple explanation

Checkpoint 1 built the evidence layer: pinned models, one normalized interface, a hard eligibility filter, a fixed GSM8K sample, exact scoring, and saved experiment records.

Checkpoint 2 puts a transparent decision layer on top of that evidence:

1. Check hard requirements, such as minimum context length.
2. Remove models that cannot satisfy them.
3. Apply a visible priority: lower cost, higher quality, faster response, or balanced.
4. Select exactly one pinned model and return a human-readable reason.

It then compares that router against two fixed baselines on the same saved benchmark results. This is an understandable baseline, not a learned router.

## Slide 1 — Adaptive LLM Router, Checkpoint 2

“Hi, I’m Mian Abdullah. In Checkpoint 1 I built the measurement layer for my Adaptive LLM Router: pinned models, a registry, a context filter, and a saved GSM8K benchmark. In Checkpoint 2 I built the routing layer on top of that evidence, and I’ll show it working live.”

## Slide 2 — Today

“Four parts, then the demo. What changed since Checkpoint 1, how the rule-based router decides, the benchmark evidence and results dashboard, and the tests that show priorities and hard requirements working.”

## Slide 3 — Evidence → decision

“Every request goes through the same four steps. The prompt comes in with the user’s priority. The filters run first, so a preference can never pick a model that fails a hard requirement. Then the rule applies the priority and some visible prompt signals, and the system returns exactly one pinned model with its reason. There is no hidden fallback to another model.”

## Slide 4 — Rule routing · three roles

“For this checkpoint I added a dated three-model paid pool, so each priority now has a distinct role. Lower cost goes to Gemma 4 26B, the cheapest. Faster response goes to Mercury 3. Higher quality goes to Gemini 4 Argon. Balanced counts visible signals such as math, code, long prompts, or many numbers: no signals uses Gemma, one or two uses Mercury, three or more uses Gemini. The GSM8K, latency, and price rows are measured, and the next slide shows where they come from.”

## Slide 5 — CP2 • Benchmark evidence

“To compare strategies fairly I need saved results. I ran the exact same twelve GSM8K questions, prompt, and settings as Checkpoint 1 through the paid pool: 36 results. Gemini got all twelve, Gemma eleven, Mercury ten. Mercury’s two misses were empty provider responses, and I kept them as failures instead of dropping them. The runner showed a worst-case cost estimate first and has a one-dollar cap; the whole run cost about two cents. The Checkpoint 1 free-pool evidence, where Gemma hit nine rate limits, is kept unchanged.”

## Slide 6 — Results dashboard

“This is the results dashboard. Each strategy picks one saved result per question, so the comparison is controlled and costs nothing to rerun. Cost priority matches the fixed cheapest baseline and quality priority matches the fixed strongest baseline, which is what the rules say should happen. Balanced got all twelve right, the same as always using Gemini, for about 45 percent less cost and a six-times faster median.

I want to be careful about that. Mercury’s two failures happened on prompts the rule had already sent to Gemini, which helped, and part of that is luck. Twelve math questions are evidence for this setup, not a general ranking, and I didn’t tune the thresholds on these outcomes.”

## Slide 7 — Policy tests • same prompt

“Here is the priority control. Same prompt, one change. Lower cost previews Gemma. Higher quality previews Gemini Argon. If I keep Lower cost but require 500,000 tokens of context, Gemma is filtered out first because it supports 262,144, so the next-cheapest eligible model, Mercury, is chosen and the explanation says why. Every preview shows the selected model, the eligible set, and the reason, without a provider call. Twelve fixed acceptance cases check this automatically: five for the free pool and seven for the paid pool.”

## Slide 8 — What shipped

“This is the real Route screen. Everything my proposal listed for Checkpoint 2 runs in the app: the fixed and rule baselines, the priority and context controls, the paid pool with its 36-cell matrix, and the results dashboard with the per-prompt view. Let me show it.”

Switch to the browser and follow [the live demo guide](live-demo-guide.md):

1. Paid-pool acceptance matrix, 7/7.
2. Same prompt: Lower cost → Gemma, Higher quality → Gemini Argon.
3. 500,000-token requirement → Mercury, with the override reason.
4. One real routed call: response, latency, tokens, cost.
5. Results dashboard, then the per-prompt view for the balanced strategy.

## Slide 9 — What I learned

“The main lesson was that shared free endpoints made availability, not answer quality, the dominant result. My response was to add a dated paid pool on the same protocol, keep every failure visible, and compare strategies offline on saved results. Next, for Checkpoint 3, is a learned router: a train, validation, and held-out split, prompt and model features, and a second task category, compared against these baselines. Thank you. I’m happy to take questions.”

## Likely questions

**Why not just always use the strongest model?** On this matrix it costs about 1.8 times as much as balanced routing for the same 12/12 and is about six times slower at the median. The project is about when that extra cost is worth it.

**Isn’t 12/12 for balanced routing just luck?** Partly. Mercury’s two failures landed on prompts the rule had already sent to Gemini. That is why I report it as evidence for this setup and why Checkpoint 3 adds held-out prompts and another task category.

**Did you tune the rule on the test data?** No. The signal definitions are unchanged from Checkpoint 1, and the three-signal tier was written before the paid run finished. With only 12 prompts there is no separate tuning set yet; Checkpoint 3 adds one.

**Why keep the free pool?** It is the preserved Checkpoint 1 evidence. Changing it would break comparability. The paid pool is a separately versioned snapshot.

**What happens if a model’s price changes?** The live preflight compares catalog price and context length with the dated snapshot and refuses to route on drift rather than silently using different terms.

**What does the router do if the chosen model fails?** It reports the failure. It never quietly calls a different model.
