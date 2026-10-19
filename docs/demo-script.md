# Checkpoint 2 demo script

Use this as the short version of the full [presentation script](presentation-script.md).

## Before the room

1. Run `./scripts/check.ps1`.
2. Run `./scripts/demo.ps1`.
3. Open `http://127.0.0.1:8000` and leave the server terminal running.
4. Open `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx`.
5. Keep `docs/demo/checkpoint-2-backup-demo.webm` open as a fallback.
6. Never project `backend/.env` or any API credential.

## Three-minute application walkthrough

1. **Lower cost:** on Route, keep minimum context at `1`, select **Lower cost**, and preview. Gemma is selected.
2. **Higher quality:** select **Higher quality** and preview the same prompt. Nemotron is selected.
3. **Hard requirement:** return to **Lower cost**, click **Use 500,000 demo**, and preview. Gemma is excluded before the priority rule, so Nemotron is selected.
4. **Explanation:** point to the selected model, eligibility count, required context, and human-readable reason. Emphasize that preview makes no provider call.
5. **Replay:** scroll to the saved strategy matrix and show accuracy, availability, latency, and known cost for the fixed and rule baselines.
6. **Evidence:** open Benchmark and expand one saved record. Explain that the 24 logical cells are committed evidence from Checkpoint 1.

## One-sentence message

“Checkpoint 1 collected reproducible evidence; Checkpoint 2 uses that evidence in a transparent baseline router that applies hard requirements before user preferences.”

## If asked to make a live provider call

Use **Route prompt** once. It sends one request to the already selected model. If the provider is rate-limited, keep the result visible and explain that the failure is real operational evidence. Do not retry repeatedly and do not start the full benchmark.
