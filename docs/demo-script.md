# Checkpoint 1 demo script

## Before the room

1. Revoke any OpenRouter key that has appeared in chat.
2. Put a replacement key only in `backend/.env`.
3. Run `./scripts/check.ps1`.
4. Run the four-call pilot on an earlier day if the provider's free quota is tight.
5. Complete and sanitize the full benchmark.
6. Run `./scripts/demo.ps1` and open `http://127.0.0.1:8000`.
7. Keep the backup recording and tagged repository available.

## Five-minute walkthrough

1. **Orient:** point out that this is the evidence layer, not the final router.
2. **Compare:** submit one prompt, showing the same input, two fixed model IDs, independent latency, tokens, cost, and failure states.
3. **Filter:** switch to Eligibility and evaluate 500,000 tokens. Explain why Gemma is rejected before a model call.
4. **Benchmark:** show the locked GSM8K protocol, the saved 24-cell run, aggregate accuracy/latency/tokens, and one expanded record.
5. **Reproducibility:** identify the dataset revision, registry checksum, Git commit, append-only attempts, and resume behavior.
6. **Boundary:** state that learned routing, Jev, local models, and broader benchmarks begin only after this checkpoint.

Do not trigger the full live run during the presentation. Use the saved run and reserve live calls for the short comparison.
