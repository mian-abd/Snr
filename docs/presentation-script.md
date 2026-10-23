# Checkpoint 2 presentation script

This script follows `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx` (9 slides). It runs about seven minutes before the live demo, at roughly 45 seconds per slide. The same text is in each slide's speaker notes in shorter form.

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

## Slide 2 — Three Checkpoint 2 commitments, all delivered

“My proposal listed three things for today. First, two fixed-model baselines and a rule-based router compared on the same benchmark data for accuracy, response time, and cost. Second, priority controls, so the same prompt routes differently when the user changes what matters. Third, a results dashboard that shows the selected model and summary results. All three are in the Route tab, and the bottom of each card says where.”

## Slide 3 — Hard requirements first, priority second, one model out

“Every request goes through the same four steps. The hard filter runs first, so a preference can never pick a model that fails a requirement. Then the priority decides, and the system returns exactly one pinned model with its reason. There is no hidden fallback.

For this checkpoint I added a dated three-model paid pool, so each priority now has a distinct role. Lower cost goes to Gemma 4 26B, the cheapest. Faster response goes to Mercury 3. Higher quality goes to Gemini 4 Argon. Balanced counts visible prompt signals, such as math, code, long prompts, or many numbers: no signals uses Gemma, one or two uses Mercury, three or more uses Gemini. It is hand-written and every signal is shown.”

## Slide 4 — Change one setting, get a different model

“Here is the same prompt with one change. With Lower cost, the router previews Gemma. With Higher quality, it previews Gemini Argon. Preview runs the real policy locally and makes no provider call.

The bottom left is the hard requirement. If I require 500,000 tokens of context, Gemma is removed first because it supports 262,144. Even with a cost preference, it can’t be chosen, so the next-cheapest eligible model, Mercury, is selected, and the explanation says so. Twelve fixed acceptance cases check these behaviors automatically: five for the free pool and seven for the paid pool.”

## Slide 5 — Same 12 GSM8K questions, two model pools

“The strategies are compared on saved benchmark results, so the data matters. Checkpoint 1 used two free models, and availability dominated: nine of Gemma’s twelve cells were shared free-tier rate limits, not wrong answers.

So for Checkpoint 2 I ran the exact same twelve questions, prompt, and settings through the paid pool. Gemini got all twelve, Gemma eleven, and Mercury ten. Mercury’s two misses were empty provider responses, and I kept them as failures instead of dropping them. The runner showed a worst-case estimate first and has a one-dollar cap. The whole paid run actually cost about two cents.”

## Slide 6 — Six strategies on the same 36 saved cells

“This is the results dashboard. Each strategy chooses one saved result per question, so the comparison is controlled and costs nothing to rerun. Cost priority matches the fixed cheapest baseline and quality priority matches the fixed strongest baseline, which is what the rules say should happen. The highlighted row is balanced. In the app I can also switch to the free Checkpoint 1 matrix and see the same six strategies there.”

## Slide 7 — Balanced routing matched the strongest model for less

“On this matrix, balanced routing got all twelve right, the same as always using Gemini, for about 45 percent less cost and a six-times faster median response.

I want to be careful about what that means. The seven prompts with fewer signals went to Mercury and were all correct. Mercury’s two failures happened on prompts the rule had already sent to Gemini, which helped, and part of that is luck. Twelve math questions are evidence for this setup, not a general ranking. The thresholds were set before the paid run finished and I didn’t tune them afterward.”

## Slide 8 — What I will show, in order

“Now the live demo. I’ll show the acceptance matrix, the same prompt under two priorities, the 500,000-token override, one real routed call, the dashboard, and the per-prompt decisions. Everything except the one real call works offline from committed evidence, and there’s a backup recording in the repository.”

Switch to the browser and follow [the live demo guide](live-demo-guide.md).

## Slide 9 — What this does not show yet, and what comes next

“The limits are part of the result: twelve questions from one task family, hand-written signals, and priorities that map to model roles instead of predicted success.

Checkpoint 3 is the learned router: a train, validation, and held-out test split, prompt and model features, logistic regression and gradient boosting, and a second task category, all compared against these baselines on held-out prompts. Thank you. I’m happy to take questions.”

## Likely questions

**Why not just always use the strongest model?** On this matrix it costs about 1.8 times as much as balanced routing for the same 12/12 and is about six times slower at the median. The project is about when that extra cost is worth it.

**Isn’t 12/12 for balanced routing just luck?** Partly. Mercury’s two failures landed on prompts the rule had already sent to Gemini. That is why I report it as evidence for this setup and why Checkpoint 3 adds held-out prompts and another task category.

**Did you tune the rule on the test data?** No. The signal definitions are unchanged from Checkpoint 1, and the three-signal tier was written before the paid run finished. With only 12 prompts there is no separate tuning set yet; Checkpoint 3 adds one.

**Why keep the free pool?** It is the preserved Checkpoint 1 evidence. Changing it would break comparability. The paid pool is a separately versioned snapshot.

**What happens if a model’s price changes?** The live preflight compares catalog price and context length with the dated snapshot and refuses to route on drift rather than silently using different terms.

**What does the router do if the chosen model fails?** It reports the failure. It never quietly calls a different model.
