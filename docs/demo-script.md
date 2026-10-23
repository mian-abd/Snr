# Checkpoint 2 demo script

Use this as the short version of the [presentation script](presentation-script.md) and [live demo guide](live-demo-guide.md).

## Before the room

1. Run `./scripts/check.ps1`.
2. Run `./scripts/demo.ps1`.
3. Open `http://127.0.0.1:8000` and leave the server terminal running.
4. Open `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx`.
5. Keep `docs/demo/checkpoint-2-backup-demo.webm` ready as a fallback.
6. Never project `backend/.env` or any API credential.

## Three-minute application walkthrough

1. **Acceptance matrix:** Route, paid pool, 7/7 expected-versus-actual cases pass with no provider call.
2. **Lower cost:** minimum context `1`, **Lower cost**, preview. Gemma 4 26B is selected.
3. **Higher quality:** same prompt, **Higher quality**, preview. Gemini 4 Argon is selected.
4. **Hard requirement:** **Lower cost**, **Use 500,000 demo**, preview. Gemma is excluded first; Mercury 3 is selected and the reason explains the override.
5. **One live call:** context back to `1`, **Route prompt**. One request, with response, latency, tokens, and cost.
6. **Dashboard:** six strategies over the 36 saved paid cells. Balanced: 12/12, $0.0116 vs. $0.0209 for always-Gemini.
7. **Per prompt:** balanced strategy, model and reason per question.
8. **Optional:** switch to the Checkpoint 1 free pool to show the original 24-cell evidence.

## One-sentence message

“Checkpoint 1 collected reproducible evidence; Checkpoint 2 uses that evidence to compare fixed baselines with a transparent router that applies hard requirements before user preferences.”

## If the live call fails

Leave the failure visible. It is real operational evidence, and the router never substitutes another model. Do not retry repeatedly and do not start a benchmark run while presenting.
