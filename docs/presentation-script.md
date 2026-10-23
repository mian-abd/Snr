# Checkpoint 2 presentation script

This script follows `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx`. It is written for about seven minutes plus the live demo and questions. The safest demo is the local **decision preview** and saved benchmark replay; neither one spends provider calls or depends on free-provider availability.

## The simple explanation

Checkpoint 1 built an evidence layer: two fixed models, one normalized interface, a hard eligibility filter, a fixed GSM8K sample, objective scoring, and saved experiment records.

Checkpoint 2 puts a transparent decision layer on top of that evidence. A request now follows this order:

1. Check hard requirements, such as minimum context length.
2. Remove models that cannot satisfy those requirements.
3. Apply a visible priority: lower cost, higher quality, faster response, or balanced.
4. Select exactly one pinned model.
5. Return the selected model and a human-readable reason.

This is an understandable baseline, not a learned router. That distinction is important.

## Slide 1 — Adaptive LLM Router, Checkpoint 2

Say:

“Hi, I’m Mian Abdullah. In Checkpoint 1 I built the measurement layer for my Adaptive LLM Router. In this checkpoint I moved from comparing models to making a transparent routing decision. The system now filters incompatible models, applies an explicit user priority, selects one fixed model, and explains why it made that choice.”

## Slide 2 — Today

Say:

“I will show four things. First, what changed since Checkpoint 1. Second, how the rule-based router works. Third, how the same prompt produces different decisions when the priority or requirement changes. Finally, I will connect those choices to the saved benchmark evidence and show the live application.”

## Slide 3 — Evidence to decision

Say:

“The key architectural change is this four-step pipeline. The prompt enters first. Hard filters run before any preference. For example, if a request needs at least 500,000 context tokens, Gemma is removed because its context window is 262,144, while Nemotron remains because it supports one million.

After filtering, the policy rule applies the user’s priority. It then selects one model and returns an explanation. The important design decision is that requirements and preferences are separate. A lower-cost preference is allowed to choose only among models that can actually satisfy the request.”

Transition:

“Now I will explain what the current rules mean.”

## Slide 4 — Rule routing and transparent decisions

Say:

“The two candidates stay pinned to the same exact OpenRouter model IDs used in Checkpoint 1: Google Gemma 4 26B and NVIDIA Nemotron 3 Ultra.

The cost-oriented and latency-oriented baselines prefer Gemma, the smaller model. Both endpoints were free in this experiment, so the cost rule is currently a transparent smaller-model proxy, not proof of a measured price advantage. The latency rule is supported only by the successful calls in this small run: Gemma averaged about 5.6 seconds when it was served, while Nemotron averaged about 19.9 seconds. Gemma was available for only three of twelve cells, so I do not present latency without that reliability caveat.

The quality-oriented baseline prefers Nemotron because it scored eight correct answers out of twelve logical cells, compared with Gemma’s three out of twelve. A 500,000-token hard requirement also leaves only Nemotron eligible.

Every decision records the priority, required context, eligible models, excluded models, selected model, policy version, and explanation. There is no hidden fallback.”

## Slide 5 — Baseline evidence

Say:

“These rules are connected to the saved Checkpoint 1 matrix rather than invented performance claims. The experiment contains twelve fixed GSM8K questions for each of two models, so there are twenty-four logical result cells.

Nemotron successfully served all twelve cells and scored eight exact numeric matches, which is 66.7 percent across the fixed sample. Its mean successful latency was about 19.9 seconds.

Gemma served three of twelve cells and those three answers were correct. Nine cells ended in upstream shared-pool rate limits. Because failed cells remain in the twelve-cell denominator, the demonstrated accuracy is three out of twelve, or 25 percent, and availability is shown separately.

The important point is not that this tiny sample proves one model is universally better. The point is that quality, latency, cost, and availability are preserved as separate evidence instead of being hidden.”

## Slide 6 — Policy tests

Say:

“This slide shows the same behavior as the five-case acceptance matrix in the application. The matrix automatically verifies cost, latency, and quality priorities, a balanced math prompt, and the 500,000-token hard-requirement override. It shows expected and actual models, and all five cases pass locally without an OpenRouter call.

For the interactive test, I keep the prompt unchanged and change one control at a time.

With no restrictive context requirement, the lower-cost or faster-response priority selects Gemma. The higher-quality priority selects Nemotron. Then I choose lower cost again but require at least 500,000 context tokens. Gemma is filtered out first, so Nemotron is selected even though the preference asked for the smaller model.

That behavior proves the router treats a hard requirement as non-negotiable and a priority as a preference. The preview endpoint returns the full decision explanation locally and does not call OpenRouter. The acceptance matrix makes the test repeatable instead of depending only on my manual clicks.”

### Live demo at this point

Use the **Route** tab.

1. Scroll briefly to the **Deterministic acceptance matrix** and point out **5/5 passed**.
2. Return to the default prompt.
3. Select **Lower cost**, keep minimum context at `1`, and click **Preview decision**. Point out that Gemma is selected.
4. Select **Higher quality** and preview again. Point out that Nemotron is selected for the same prompt.
5. Select **Lower cost**, click **Use 500,000 demo**, and preview again. Read the explanation: the lower-cost rule would prefer Gemma, but the hard requirement removes it, so Nemotron is selected.
6. Scroll to the strategy replay table. Explain that it replays the saved twenty-four-cell matrix and makes no provider calls.

Do not rely on **Route prompt** for the main presentation. It is a real provider call and free capacity may be rate-limited. The live UI and local preview are real application behavior even though inference is not called.

## Slide 7 — What shipped by October 15

Say:

“By the October 15 milestone, the application included fixed baselines, a rule router, four priority controls, the context requirement control, an explanation view, and an offline strategy dashboard. The final checkpoint build also includes a five-case expected-versus-actual acceptance matrix, so the policy rules are visible and repeatable in the UI.

The screenshot is the actual production UI. The dashboard replays the same saved evidence under six strategies: two fixed baselines plus cost, quality, latency, and balanced rule policies. Because it uses committed records, I can demonstrate routing behavior even when a free provider is unavailable.

The implementation also has automated backend, frontend, and end-to-end tests. The policy can be previewed without a key, while a live routed response still keeps the credential on the backend.”

## Slide 8 — What I learned

Say:

“The main lesson is that model quality and provider availability are different measurements. A capable model may still be unavailable through a shared free endpoint. A robust router must preserve that distinction.

My response was to add a deterministic preview and saved-evidence replay. That gives me a reliable demo path without hiding real provider failures.

The next phase is learned routing. I will keep these fixed and rule-based strategies as baselines, expand the evaluation evidence, and measure whether a trained policy actually improves the quality, latency, cost, and availability trade-off.”

Close with:

“That is Checkpoint 2: evidence first, then a transparent decision. I’m happy to take questions.”

## Questions you may receive

### Is this already an intelligent or learned router?

“No. It is a deterministic and explainable baseline. I need that baseline before I can claim that a learned policy improves anything. The next phase compares learned routing against the same fixed evidence and metrics.”

### Why does lower cost choose Gemma if both models are free?

“In this checkpoint it is explicitly a smaller-model proxy. The current run reports zero cost for both free endpoints, so I do not claim a measured dollar advantage. The interface and policy are structured so real price metadata can replace that proxy in a later benchmark version.”

### Does 66.7 percent prove Nemotron is better?

“No. Twelve GSM8K questions are a functional checkpoint, not a statistically conclusive leaderboard. The result supports this small baseline demonstration and shows that the evidence pipeline works.”

### Why count provider failures in accuracy?

“The dashboard treats each model-question pair as a logical routing outcome. If the chosen route cannot return an answer, that route did not solve the request. I still show availability separately so the audience can distinguish reasoning quality from service reliability.”

### Why not keep retrying Gemma until it answers?

“Unlimited retries would hide the operational cost of choosing an unavailable route and make latency comparisons misleading. Retries are bounded and every attempt is preserved.”

### What does balanced mean?

“Balanced is a small visible rule set. Math, code, long prompts, or prompts with several numeric values prefer Nemotron; simpler prompts prefer Gemma. It is intentionally easy to inspect and is not presented as a learned quality predictor.”

### What happens if the live provider fails during the presentation?

“The decision preview and strategy replay remain fully functional because they are local and based on versioned metadata and saved results. Provider failure is displayed honestly rather than hidden.”

## Final presenter checklist

- Start the app with `./scripts/demo.ps1` and open `http://127.0.0.1:8000`.
- Use **Preview decision**, not repeated live routing, for the main demonstration.
- Show the **5/5 passed** policy matrix before the manual preview.
- Keep the backup video `docs/demo/checkpoint-2-backup-demo.webm` open in another window.
- Keep the PowerPoint deck in `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx`.
- Do not show `backend/.env` or any API credential.
- Do not start a new full benchmark during the presentation.
