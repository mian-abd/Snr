# Live demo guide (Checkpoints 2 and 3)

Checkpoint 2 comes first; the Checkpoint 3 walkthrough is at the end.

## Start the production application

From the repository root in PowerShell:

```powershell
./scripts/demo.ps1
```

Open `http://127.0.0.1:8000` and leave the PowerShell window running. FastAPI serves both the built React application and the API from this address. The header should show **Backend online** and **OpenRouter ready**.

Everything except step 4 works without a provider call: decision previews, acceptance matrices, both saved matrices, the dashboard, and the Benchmark records.

## Walkthrough (about four minutes)

### 1. Paid-pool acceptance matrix

Open **01 Route**. Make sure **Checkpoint 2 paid pool** is selected (it is the default). Scroll to the policy acceptance matrix and show **7/7 passed**. Point out the expected and actual model columns and the 500,000-token override case.

Say: “These are fixed reference prompts. They make no provider call and prove the rules behave as documented.”

### 2. Same prompt, two priorities

1. Paste: `A store sells 3 notebooks for $4.50 each and 2 pens for $1.25 each. Calculate the total cost.`
2. Keep minimum context at `1`, select **Lower cost**, click **Preview decision**. Gemma 4 26B A4B is selected.
3. Select **Higher quality**, preview again. Gemini 4 Argon is selected.

Say: “I changed only the priority, not the prompt.”

### 3. Hard requirement overrides the preference

1. Select **Lower cost**.
2. Click **Use 500,000 demo**, then **Preview decision**.
3. Read the reason: the cost preference would pick Gemma, but Gemma (262,144) is excluded first, so the next-cheapest eligible model, Mercury 3, is selected. The eligibility line shows two eligible models.

### 4. One real routed call

Set the minimum context back to `1`, keep **Lower cost**, and click **Route prompt**. One request goes to Gemma after credential and catalog preflight. Show the response, latency, tokens, and provider-reported cost (a tiny fraction of a cent).

If the provider fails, leave the failure visible and explain that the system reports real failures and never substitutes another model. Do not retry repeatedly.

### 5. Results dashboard

Scroll to **Results dashboard**. Walk through the six strategies over the 36 saved paid cells: accuracy, served cells, median and p95 latency, total cost, and cost per correct answer. Point to the balanced row: 12/12 for $0.0116 against $0.0209 for always-Gemini.

### 6. Per-prompt decisions

In **Per-prompt routing decisions**, keep **Rule router: balanced priority**. Show one question routed to Mercury with two signals and one routed to Gemini with three, and point to the outcome chips that show what every saved model did on that question (GSM8K #1227 and #1251 show Mercury’s empty responses).

### 7. Optional: the other tabs

- **02 Compare** (paid pool): **Compare 3 models** sends the same prompt to Gemma, Mercury, and Gemini Argon and shows three result cards with latency, tokens, and cost.
- **03 Eligibility:** all five registry entries from both pools; at 500,000 tokens both Gemma entries are excluded.
- **04 Benchmark** (paid pool): the saved 36-cell run and its records. **Run pilot** shows the worst-case estimate and cap first. Click **Cancel** during a presentation unless you mean to spend.

### 8. Optional: compare with Checkpoint 1

Scroll up, click **Checkpoint 1 free pool**. The acceptance matrix becomes 5/5 and the dashboard replays the original 24 free-tier cells, where Gemma’s nine rate limits dominate. Open **04 Benchmark** to expand a raw saved record if asked.

## Fallbacks

1. If OpenRouter is unavailable, skip step 4. Everything else is local.
2. If the browser closes, reopen `http://127.0.0.1:8000`.
3. If the server stops, rerun `./scripts/demo.ps1`.
4. If the application cannot be restarted, play `docs/demo/checkpoint-2-backup-demo.webm`.
5. Keep the deck `docs/presentations/Adaptive_LLM_Router_Checkpoint_2_Final.pptx` open locally.

## Security rules

- Never open or project `backend/.env`.
- Never paste the OpenRouter key into the browser UI.
- Keep manual prompt saving off unless the prompt is safe to store.
- Do not claim the 12-question sample is a statistically conclusive ranking.
- Describe Gemma’s nine Checkpoint 1 failures as provider rate limits, and Mercury’s two as empty provider responses, not wrong math answers.

## Checkpoint 3 live demo (Learned tab)

Start the app the same way (`./scripts/demo.ps1`, then `http://127.0.0.1:8000`) and open **05 Learned**. The prompt box already holds the demo prompt: "A train travels 180 km in 2.5 hours. What is its average speed in km/h?" Previews make no provider call.

1. **Higher quality**, then **Preview decision**: Gemma 4 26B A4B, "math (inferred)". For math, Gemma is about as accurate as Gemini at a small fraction of the cost.
2. **Faster response**, then **Preview decision**: Mercury 3.
3. **Lower cost**, then **Preview decision**: gpt-oss-120b (free).
4. Keep **Lower cost**, set **Minimum context** to `500000`, then **Preview decision**: Nemotron 3 Ultra 550B (free). Gemma, gpt-oss-120b, Llama 3.3 70B and both Qwen models show "Context … is below the required 500,000 tokens".
5. Set **Minimum context** back to `1`, keep **Lower cost**, then **Route prompt**: one real call to gpt-oss-120b, status success, 72 km/h, free.
6. Scroll to **Checkpoint 3 comparison** and click **MMLU-Pro** to redraw both plots for that task. The **Oracle gap and routing errors** table is just below.

Checkpoint 3 fallbacks:

- **OpenRouter key expired or missing:** live calls to OpenRouter models fail with a 401, but previews and step 5 still work. The key in `backend/.env` expired on 2026-11-12 and must be replaced before demoing paid routes.
- **The free OVHcloud endpoint times out:** the app reports the failure. Say so, and do not retry more than once.
- **The application cannot be restarted:** play `docs/demo/checkpoint-3-backup-demo.webm`. The deck is `docs/presentations/Adaptive_LLM_Router_Checkpoint_3.pptx`.
