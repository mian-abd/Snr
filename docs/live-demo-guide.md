# Live UI demo guide

## Start the application

From the repository root in PowerShell:

```powershell
./scripts/demo.ps1
```

Then open:

```text
http://127.0.0.1:8000
```

The script builds the React frontend and starts FastAPI, which serves the application and API from that one local address. Leave the PowerShell window open while you present.

If the `uv` command is unavailable in a newly opened terminal, restart the terminal after installing `uv`, or run the backend with the project virtual environment:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.cli serve
```

The production UI still loads the committed benchmark evidence without an API key. A live comparison needs `OPENROUTER_API_KEY` in ignored `backend/.env`.

## What to show

### 1. Compare

Enter a short non-sensitive prompt. The app calls the two pinned models concurrently. Show that each card has a requested model, served model, result text or error, latency, tokens, and cost.

Do not promise both free endpoints will answer. Gemma can return a shared-pool rate limit. A partial result is a valid demonstration of independent failure handling.

### 2. Eligibility

Keep the minimum context at `500000`, then click **Evaluate**. Explain the concrete result:

- Gemma: `262144 < 500000`, excluded
- Nemotron: `1000000 >= 500000`, eligible

### 3. Benchmark

Open the Benchmark tab. It automatically loads the committed saved run:

- 12 fixed GSM8K questions
- 2 pinned models
- 24 completed logical cells
- temperature 0
- maximum 512 output tokens
- exact numeric match

Expand one result record. Explain that the view displays persisted evidence and does not send a new provider request.

## Presentation-safe behavior

- Never paste or show the OpenRouter API key.
- Keep “Save locally” off for ordinary prompts.
- Do not click **Run benchmark** during the presentation.
- If a live comparison fails, move directly to Benchmark and explain the recorded failure state.
- If the UI will not start, use the published release and attached video: <https://github.com/mian-abd/Snr/releases/tag/checkpoint-1>.
