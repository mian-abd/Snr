# Presentation script for Checkpoint 1

This script follows `Adaptive LLM Router.pptx` and the live application as it stands today. It is designed for six minutes, plus questions.

## The one idea to keep in mind

Checkpoint 1 does **not** claim that it has already built a smart router. It builds the measurement layer a router needs: fixed model identities, comparable response fields, hard capability filtering, an objective scorer, saved evidence, and visible provider failures.

The current Compare screen is a valid demonstration when Gemma is rate-limited and Nemotron succeeds. Say that the screen records two independent provider outcomes. Do not say that Gemma gave a bad answer. It did not return an answer at all.

## Before presenting

1. Keep the local app open at `http://127.0.0.1:8000` and leave the current Compare result visible.
2. Do not submit another prompt unless you have already confirmed both providers are available. The visible screen already demonstrates the feature.
3. Open the Benchmark tab once before presenting, then return to Compare.
4. Keep the release page open in another tab as a backup.

Important corrections to the slides:

- Slide 4 contains placeholder names, `gpt-4o` and `claude-3-5-sonnet`. The live application compares **Google Gemma 4 26B A4B** and **NVIDIA Nemotron 3 Ultra 550B** through OpenRouter.
- Slide 6 spells **Nemotron** incorrectly as “Nemetron.” Say the correct name aloud.

## Slide 1: Title

“Hi, I’m Mian Abdullah. This is Checkpoint 1 of my Adaptive LLM Router. The long-term project will choose an appropriate language model for each request. Before building that policy, I needed a reliable way to collect evidence about models.”

## Slide 2: Agenda

“I will briefly explain the problem, show the live comparison console, explain the fixed GSM8K experiment, show the context-window filter, and then summarize what the first run taught me.”

## Slide 3: What I am building

“One prompt can be handled by many models, but they differ in latency, cost, context capacity, quality, and availability. A router should not make a choice based only on a model name.

This checkpoint builds the layer underneath the router. It stores model metadata, rejects models that fail a hard requirement, calls fixed model identities through one interface, and records the result of an objective benchmark. Choosing the best model is deliberately deferred to the next checkpoint.”

Transition: “First, I will show the live comparison surface.”

## Slide 4: Promise 1, dual-model comparison

“In the implementation, I have pinned Gemma and Nemotron to exact OpenRouter IDs. The same prompt goes to both models concurrently. Each result has its own response text, latency, token count, cost when available, and status.

Pinning matters because the app must never label one model while a different model actually answered. The system also does not silently replace a failed model with another one.”

### Live demo: Compare tab

Point to the two cards and say:

“Here is the live Compare screen. Both cards show the same request, but their results remain independent. Nemotron completed this request, so the response, latency, tokens, and zero cost are visible on the right.

Gemma returned a provider rate limit. The application preserves that as a capacity event. It does not hide the error, call a different model, or turn the failure into a quality score. This is important because a future router needs honest reliability data before it can make a decision.”

If both models happen to return successfully on a later attempt, say:

“Each card contains a separate answer, latency, usage, and cost record. They are two independent calls under the same prompt.”

Do not say “Gemma is worse” or “the rate limit proves anything about reasoning quality.”

## Slide 5: Promise 2, objective benchmark

“For quality measurement, I used twelve fixed GSM8K grade-school math questions. Both pinned models received the same prompt template, temperature zero, and a maximum of 512 output tokens. That creates 24 model-question cells.

The saved run has 24 final records. Nemotron completed 12 calls and answered 8 correctly by exact numeric match. Gemma completed 3 calls and answered all 3 correctly. The remaining 9 Gemma cells ended in upstream rate limits.

I keep those nine cells as provider failures. I do not call them wrong answers, and I do not claim that twelve questions prove a general ranking. The purpose is to demonstrate a reproducible collection, scoring, and evidence pipeline.”

### Live demo: Benchmark tab

“This tab loads saved evidence. It does not send a new provider request. The protocol is locked: GSM8K test data, 12 questions, two fixed models, 24 cells, temperature zero, and exact numeric matching.

The summary separates quality from availability. Expanding a record shows the question, expected answer, extracted answer, response or normalized provider error, and score. The sanitized JSON evidence is committed with the project so this run can be inspected offline.”

## Slide 6: Promise 3, eligibility before inference

“The third piece is a hard eligibility filter. I set a minimum context requirement of 500,000 tokens. Gemma has 262,144 tokens, so the filter excludes it. Nemotron has one million tokens, so it remains eligible.

This is deterministic. It is not a judgment that Nemotron is smarter. It simply proves that a future router can remove models that cannot meet a non-negotiable requirement before spending money or waiting for inference.”

### Live demo: Eligibility tab

“I keep the requirement at 500,000 and evaluate it. The app shows both the decision and the exact numerical reason beside the model.”

## Slide 7: Reproducibility and engineering work

“I made the experiment recoverable and inspectable. Each provider attempt is append-only. The runner can resume interrupted work without repeating completed cells. It writes a manifest, attempt log, canonical results, and summary.

I also versioned the model registry and fail the live preflight if the catalog changes. Tests cover the registry, scoring, retries, resume behavior, sanitization, API behavior, frontend states, and the production build. Secrets remain server-side.”

## Slide 8: What I learned and what comes next

“The key lesson is that model quality and model availability are different measurements. A free endpoint can be temporarily unavailable even when the model itself is capable. The system needs to record that fact rather than hide it.

The next checkpoint will add a routing policy on top of this evidence. It can then decide among eligible models using quality, latency, cost, and operational reliability.”

## Questions you may get

### “Why is Gemma rate-limited even after several hours?”

“This is a provider-side shared-capacity limit from Google AI Studio through OpenRouter. It is separate from the app’s local request budget and does not evaluate Gemma’s reasoning quality. The app exposes that distinction clearly.”

### “Why did you keep that failure on the screen?”

“Because hiding it would make the comparison misleading. A future router needs to know when a model cannot currently serve a request. The next checkpoint can use reliability as one routing input.”

### “Why not add a third free model right now?”

“A third free model would still depend on shared provider capacity and would change the fixed two-model baseline. I tested current alternatives before the presentation; they were not reliable enough to make the demo stronger. A deliberate paid-model replacement is the proper next step if the goal is guaranteed live availability.”

### “Why only 12 questions?”

“Twelve questions demonstrate the entire pipeline within the checkpoint. They do not support a statistically strong general ranking. The saved records make expansion straightforward in the next stage.”

### “Why do you use exact match?”

“GSM8K has a canonical numeric answer. The scorer extracts the final number, parses it as a decimal, and compares it exactly. It gives no partial credit and does not use another model to judge the answer.”

### “What would you change for a production version?”

“I would use a paid, pinned provider route or a configured provider key, measure a larger evaluation set, and add an explicit routing policy. I would version every change so results stay comparable.”

## Last-minute fallback

If the local server stops or both providers fail, open the Benchmark tab or the published release. Say: “The saved checkpoint evidence is part of the release, so the evaluation remains inspectable even when a live free endpoint is busy.” Do not start the full benchmark during the presentation.
