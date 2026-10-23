# Checkpoint 2 live demo guide

## Start the production application

From the repository root in PowerShell:

```powershell
./scripts/demo.ps1
```

Open `http://127.0.0.1:8000` and leave the PowerShell window running. FastAPI serves both the built React application and the API from this address.

The main Checkpoint 2 demonstration does not require a working provider call. Decision previews, eligibility, the saved benchmark, and strategy replay all work locally.

## Recommended three-minute walkthrough

### 1. Show repeatable policy evidence

Open **01 Route**, scroll to **Deterministic acceptance matrix**, and show **5/5 passed**. Point out that the table covers cost, latency, quality, a balanced math task, and a 500,000-token requirement override. The expected and actual model columns match, and the checks make no provider calls.

### 2. Prove that priority changes the decision

Open **01 Route** and keep the minimum context at `1`.

1. Select **Lower cost**.
2. Click **Preview decision**.
3. Show that Gemma is selected and that the card says no provider call was made.
4. Select **Higher quality** and preview again.
5. Show that Nemotron is selected for the same prompt.

Explain: “I am changing the decision policy, not the prompt or model identities.”

### 3. Prove that hard requirements override preferences

1. Select **Lower cost**.
2. Click **Use 500,000 demo**.
3. Click **Preview decision**.
4. Read the explanation: Gemma would satisfy the preference, but it is excluded because `262144 < 500000`; Nemotron remains because `1000000 >= 500000`.

Explain: “The filter is a hard constraint. The priority is evaluated only among eligible models.”

### 4. Connect the decision to evidence

Scroll to **Offline strategy replay**. Show:

- fixed smaller-model baseline;
- fixed stronger-model baseline;
- cost, quality, latency, and balanced rule strategies;
- selected-model counts;
- exact-match accuracy;
- availability;
- mean successful latency;
- known cost.

Explain that this table replays `data/demo/checkpoint-1/results.jsonl` and makes no OpenRouter calls.

### 5. Show the source records

Open **04 Benchmark**. Point out the locked protocol and the saved 24 logical cells. Expand one record to show expected answer, extracted answer, score, model response or normalized provider failure, and attempt history.

## Optional live inference

Use **Route prompt** only if you already confirmed provider capacity. It sends one request to the selected model after credential and model-catalog preflight. If the provider returns a rate limit or overload, keep the result visible and explain that the system preserves real operational failures.

Do not repeatedly retry and do not start the full benchmark while presenting.

## Fallbacks

1. If OpenRouter is unavailable, continue with **Preview decision** and the saved dashboard.
2. If the local browser is closed, reopen `http://127.0.0.1:8000`.
3. If the server stops, rerun `./scripts/demo.ps1`.
4. If the application cannot be restarted, play `docs/demo/checkpoint-2-backup-demo.webm`.
5. Keep the deck `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx` available locally.

## Security rules

- Never open or project `backend/.env`.
- Never paste the OpenRouter key into the browser UI.
- Keep manual prompt saving off unless the prompt is safe to store.
- Do not claim the 12-question sample is a statistically conclusive ranking.
- Describe Gemma’s nine missing answers as provider rate limits, not wrong math answers.
