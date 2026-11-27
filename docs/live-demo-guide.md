# Live demo guide

The current site (Checkpoint 4 run-through) comes first. The Checkpoint 2 and 3 walkthroughs below it describe the earlier tabbed console and are kept as a record; their tab names no longer exist. The Gemma and Mercury steps in those older sections describe what the site did then: both models are unavailable now.

## The current site (Checkpoint 4 run-through)

Start it with `./scripts/demo.ps1`, then open `http://127.0.0.1:8000`. The pages are **Router**, **Models**, **Compare**, **Research**, **Prompts**, **FAQ**, and **Lab**. **Ctrl+K** searches all of them, and the sun / moon button switches between light and dark. The deck is `docs/presentations/Adaptive_LLM_Router_Checkpoint_4.pptx`.

The run-through follows the four things the proposal promised for Checkpoint 4:

1. Demonstrate the final routing system, including the multi-objective router that balances quality, cost and response time by the user's priority (steps 1 and 7).
2. Present the final held-out evaluation across coding, math and general question-answering (step 4).
3. Show an oracle comparison on the final evaluation set, with a few examples of better or worse choices (step 5).
4. Demonstrate one robustness test by changing one routing condition and showing the decision change, and demonstrate the complete flow from entering a prompt to receiving a routed model response (steps 2, 3 and 6).

### Before class

1. Run `./scripts/demo.ps1` from the repository root and wait for the server. Open `http://127.0.0.1:8000`.
2. Confirm Ollama is running and has the local model (the Fastest pick runs on the laptop). If it is not running, the Models page shows the local model as unavailable.
3. Check the pill at the top right: it should say 2 models are unavailable (Mercury 3 and Gemma 4 26B A4B).
4. Warm up for free: on **Router**, pick **Lowest cost** and press **Run prompt** once. It should return gpt-oss-120b and 72 km/h. This wakes the free OVHcloud endpoint for the fallback.
5. Keep the deck and the backup recording open. Never show `backend/.env`.

### Steps

The only provider call is in step 3, and it runs on the laptop. Everything else reads saved data.

1. **Router: three priorities (promise 1).** Open **Router**. The standard pool is selected and the demo prompt is already filled in ("A train travels 180 km in 2.5 hours. What is its average speed in km/h?").
   - Pick **Best quality**, then **Preview decision**: gpt-oss-120b.
   - Pick **Lowest cost**: gpt-oss-120b again, and it is free.
   - Pick **Fastest**: Qwen 3.5 9B (local). Point at the score bars in **How every model scored**: each is split into accuracy, cost, time and reliability terms. Read the end of the reason: "Without the live catalog check it would have chosen Mercury 3, which is no longer served." Point at Gemma 4 26B A4B and Mercury 3, faded as "Unavailable now".
   - Say: "One prompt, three priorities. The router balances predicted accuracy, cost and time by what the user asks for, and it only picks models that are actually served today."
2. **Stress test (promise 4, first part).** In **Stress-test this decision**, keep **Qwen 3.5 9B (local)**, pick **Gets slower**, set **×3**, and press **Simulate**. The choice moves to **DeepSeek V4 Flash**.
   - Say: "I changed one condition, the response time of one model, and the router chose differently. Nothing was sent anywhere and nothing was retrained."
3. **Complete flow (promise 4, second part).** With **Fastest** selected, press **Run prompt**. The local Qwen answers 72 km/h, and the page shows time, tokens and $0.
   - Say: "This is the whole path: the prompt, the routing decision, one real call, and the answer. It ran on my laptop through Ollama, so it was free and the prompt never left the machine."
4. **Research: the final evaluation (promise 2).** Open **Research**. Show the highlights and the leaderboard on the 300 fresh prompts (coding, math and general questions), then **Is the difference real?**.
   - Say: "The router matches the strongest model within noise, for less. Most differences here are not significant."
5. **Oracle (promise 3).**
   - On the leaderboard, press **Show** under References to show the hindsight oracle.
   - Open **Where the router goes wrong** and read the worked examples.
   - Open **Prompts**, pick **Router wrong, another model right** (4 fresh prompts), and open one to show the expected answer and every model's result, time and cost. (The **No model right** filter shows the 9 prompts nobody answered.)
   - Say: "The oracle knows the right answer in advance. It is the ceiling, and these are the prompts where my router chose worse."
6. **Robustness on all prompts (promise 4).** On **Research**, open **When prices, speed, or providers change** and pick **Fastest**: the router told about the change keeps 276 right; with its old estimates it gets 83. Then open **What your priority costs you** and move the slider to a cost weight of 0.2: 265 right for $0.0176.
   - Say: "Updating the router's facts is what saves it. And most of the cost saving arrives by a cost weight of 0.2."
7. **If time allows (promise 1).**
   - **Router**, **Model pool** → **Every model** (17 models): Best quality picks MiMo-V2.6 Flash, Fastest picks Muse Ember. More models moved the picks without a significant gain.
   - **Models**: tick **GPT-6.1 Sol** and **Gemini 4 Argon** and press **Compare**.

If someone asks what happens when a provider fails mid-run: the chosen model gets one retry, then the next-best eligible model answers once, and the page says which model failed and which answered. The tests cover this; it cannot be shown on demand.

### If something fails

- **Ollama not running (step 3):** do not run the Fastest call. Start Ollama if there is time. Otherwise, in step 2 pick **Goes offline** for Qwen 3.5 9B (local) instead of **Gets slower**: Fastest then picks DeepSeek V4 Flash. For the live call, use **Lowest cost**: it picks gpt-oss-120b on OVHcloud's free endpoint, which needs no key. It is still a third-party API, and the notice says so.
- **OpenRouter unreachable:** the pill says "Live check failed". Previews still work from the dated snapshot, and Lowest cost still works because it does not use OpenRouter.
- **Server down:** rerun `./scripts/demo.ps1` and reload.
- **The app cannot be restarted:** play `docs/demo/checkpoint-4-backup-demo.webm`.

## Checkpoint 2 walkthrough (earlier console)

### Start the production application

From the repository root in PowerShell:

```powershell
./scripts/demo.ps1
```

Open `http://127.0.0.1:8000` and leave the PowerShell window running. FastAPI serves both the built React application and the API from this address. The header should show **Backend online** and **OpenRouter ready**.

Everything except step 4 works without a provider call: decision previews, acceptance matrices, both saved matrices, the dashboard, and the Benchmark records.

## Walkthrough (about four minutes)

### 1. Paid-pool acceptance matrix

Open **02 Rule route** (it was **01 Route** at Checkpoint 2). Make sure **Checkpoint 2 paid pool** is selected (it is the default). Scroll to the policy acceptance matrix and show **7/7 passed**. Point out the expected and actual model columns and the 500,000-token override case.

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

Start the app the same way (`./scripts/demo.ps1`, then `http://127.0.0.1:8000`). It opens on **01 Learned**. The prompt box already holds the demo prompt: "A train travels 180 km in 2.5 hours. What is its average speed in km/h?" Previews make no provider call.

1. **Higher quality**, then **Preview decision**: Gemma 4 26B A4B, "math (inferred)". For math, Gemma is about as accurate as Gemini at a small fraction of the cost.
2. **Faster response**, then **Preview decision**: Mercury 3.
3. **Lower cost**, then **Preview decision**: gpt-oss-120b (free).
4. Keep **Lower cost**, set **Minimum context** to `500000`, then **Preview decision**: Nemotron 3 Ultra 550B (free). Gemma, gpt-oss-120b, Llama 3.3 70B and both Qwen models show "Context … is below the required 500,000 tokens".
5. Set **Minimum context** back to `1`, keep **Lower cost**, then **Route prompt**: one real call to gpt-oss-120b, status success, 72 km/h, free.
6. Scroll to **Checkpoint 3 comparison** and click **MMLU-Pro** to redraw both plots for that task. The **Oracle gap and routing errors** table is just below.

Checkpoint 3 fallbacks:

- **Mercury 3 retired (2026-11-12):** OpenRouter no longer serves it. Previews for Faster response and Balanced still show it, but don't route live with those presets; use Lower cost (step 5) or Higher quality. The Checkpoint 2 **02 Rule route** tab refuses live calls for the same reason.
- **OpenRouter key expired or missing:** live calls to OpenRouter models fail with a 401, but previews and step 5 still work.
- **The free OVHcloud endpoint times out:** the app reports the failure. Say so, and do not retry more than once.
- **The application cannot be restarted:** play `docs/demo/checkpoint-3-backup-demo.webm`. The deck is `docs/presentations/Adaptive_LLM_Router_Checkpoint_3.pptx`.
