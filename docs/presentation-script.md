# Presentation script for Checkpoint 1

This script follows `Adaptive LLM Router.pptx` and uses the implementation that is actually released. It is written for a presentation of about five to seven minutes.

## Before you present

1. Start the app with `./scripts/demo.ps1` from the repository root.
2. Open `http://127.0.0.1:8000`.
3. Keep the Benchmark tab open once before the presentation so you know the saved run loads.
4. Do not run the full benchmark live. Use the saved result. A live manual comparison is optional.

Important correction: Slide 4 still uses `gpt-4o` and `claude-3-5-sonnet` as visual placeholders. The application actually compares **Gemma 4 26B** and **Nemotron 3 Ultra 550B**, through OpenRouter. Say that clearly when you reach the slide. Slide 6 also spells “Nemotron” incorrectly as “Nemetron.”

## Slide 1: Title

“Hi, I’m Mian Abdullah. This is Checkpoint 1 of my Adaptive LLM Router project. The long-term goal is to choose an appropriate model for a request. This checkpoint is earlier than that: I built the evidence and measurement layer that a future router needs.”

## Slide 2: Agenda

“I’ll give the problem in thirty seconds, show the two-model comparison interface, explain the GSM8K benchmark, show the eligibility filter, and then close with what I learned from running it.”

## Slide 3: What I am building

“The core question is simple: when one prompt could go to several models, which model should answer? A real router cannot answer that responsibly without knowing which models are available, what they cost, how fast they respond, and how they perform on a defined task.

Checkpoint 1 does not make the final model choice. It collects reliable evidence first. The flow on this slide is: receive a prompt, eliminate models that cannot meet hard requirements, later choose an eligible model, and return a response.”

Transition: “Now I’ll show the first piece of that evidence layer.”

## Slide 4: Promise 1, dual-model comparison

“The first promise is one prompt, one interface, and two independent model calls. The slide uses placeholder model names, but the live system uses Gemma and Nemotron. I pinned those exact IDs so every result stays attributable to a known model.

For each model, the app shows the answer, latency, token usage, cost when the provider reports it, and a failure state. The system does not silently fall back to a different model. That matters because a comparison would be misleading if the label said one model but another model actually answered.”

### Live demo: Compare tab

Say: “Here is the live Compare screen. I can enter one prompt and the server sends it to both fixed models at the same time. The save option is off by default so ordinary prompts remain local.”

Type a harmless prompt, such as: `Explain in two sentences why reproducible model IDs matter in an experiment.`

If both return: “These are two separate results with their own timing and usage fields.”

If Gemma rate-limits: “This is useful behavior to see. The application keeps Nemotron’s independent result visible and reports Gemma’s provider failure instead of hiding it or substituting another model.”

## Slide 5: Promise 2, objective benchmark

“The second promise is an objective benchmark. I used twelve fixed questions from GSM8K, a grade-school math benchmark. Each question went to both pinned models under the same settings, giving twenty-four logical cells.

The saved result shows that Nemotron completed all twelve calls and got eight exact numeric answers. Gemma completed three calls and got three exact answers. Nine Gemma calls hit upstream shared-pool rate limits on the free endpoint.

I preserve those rate limits as provider failures. I do not count them as wrong math answers, and I do not claim this twelve-question sample proves one model is generally better. It proves that the system can capture success, quality, cost, speed, and operational failure honestly.”

### Live demo: Benchmark tab

Say: “This is the saved run. It loads without making new model calls. The protocol is locked: GSM8K test questions, two fixed models, twenty-four cells, temperature zero, and exact numeric matching.”

Point to:

- `24 / 24` completion
- the two model summary rows
- the Gemma failure count
- one expandable saved result record

Say: “Each expandable record shows the original question, expected answer, extracted answer, model response or normalized error, and score. The underlying sanitized JSON is committed with the release, so the demo remains inspectable offline.”

## Slide 6: Promise 3, eligibility before inference

“The third promise is a hard eligibility filter. Before a future router spends money or time on a model, it should remove models that cannot meet a non-negotiable requirement.

Here the requirement is at least 500,000 context tokens. Gemma has 262,144, so it is excluded. Nemotron has one million, so it remains eligible. This is deterministic metadata filtering, not a subjective model-quality judgment.”

### Live demo: Eligibility tab

Say: “I set the minimum context to 500,000 and click Evaluate. The reason appears next to each model. This function is deliberately simple and pure so a future router can reuse it.”

## Slide 7: Above and beyond

“I also made the checkpoint reproducible. The benchmark can resume rather than duplicate finished work. It records append-only attempts and final results. It sanitizes evidence before committing it. Tests and GitHub Actions check the backend, frontend, generated API schema, production build, and secret patterns. I tagged the release as `checkpoint-1` and attached a short backup walkthrough.”

## Slide 8: What I learned

“The important lesson was operational rather than theoretical: free shared model endpoints can fail for reasons unrelated to the model’s reasoning ability. The system must make that visible. If a provider rate-limits a model, replacing it silently or treating the failure as a wrong answer would distort the evidence.

My next step is to build an actual routing policy on top of this evidence layer, rather than guessing from model names or a single benchmark.”

## Questions you may get

### “Why only 12 questions?”

“Twelve questions are enough to demonstrate the full collection and scoring pipeline within the checkpoint. They are not enough for a statistically strong model ranking. A later checkpoint will expand the evaluation.”

### “Why did you use free endpoints?”

“The checkpoint needed a low-cost reproducible baseline. The rate limits became a useful test of whether the system can record operational failures honestly.”

### “Why not route automatically already?”

“Automatic routing would be premature. First I needed pinned model identities, hard constraints, comparable result fields, a scorer, evidence storage, and failure handling.”

### “What does exact match mean here?”

“The scorer extracts a final numeric answer, parses it as a decimal, and compares it to GSM8K’s canonical answer. It gives no partial credit and does not use another model as a judge.”

### “What happens if a model changes?”

“Before any live comparison or benchmark, the system checks the current OpenRouter catalog against the committed registry snapshot. It fails closed on metadata drift instead of silently switching models.”

## Last-minute fallback

If the local server or an API call fails, open the published release and say: “The saved benchmark evidence and recording are attached to the tagged release.” Then walk through the result summary in the release notes. Do not attempt a full re-run during the presentation.
