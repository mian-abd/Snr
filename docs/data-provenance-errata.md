# Data provenance errata

## GSM8K revision and checksum recorded in Checkpoints 1 and 2 (found 2026-10-27)

The Checkpoint 1 sample metadata (`data/benchmarks/gsm8k_checkpoint1.meta.json`), every benchmark manifest built from it (Checkpoint 1 free-pool runs and the Checkpoint 2 paid-pool runs), `CONTEXT.md`, and `docs/build-handover.md` record:

- dataset revision `b0bb162abedc65e1fdd8e93ed090fd7598ee68bc`
- source checksum `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14`

Neither value can be verified:

- `openai/gsm8k` on Hugging Face has no commit `b0bb162…`; the Hub API returns "Revision Not Found". The dataset's real commit history (most recent first) is `740312a` (2026-03-23), `cc7b047`, `7cf1290` (2025-12-20), `e53f048` (2024-01-04, "Convert dataset to Parquet"), `25fb041`, `be45a9e`, and earlier.
- `3730d3…` matches neither the source test file (below) nor the committed sample file (`gsm8k_checkpoint1.jsonl`, SHA-256 `4f7e8e1264f2b4e1cfeab30c6344f2c1c2c69b115548a9a7d319945b98b0ba7c`).

What is verified:

- The test split file `main/test-00000-of-00001.parquet` is byte-identical at every commit from `e53f048` through `740312a`: 1,319 rows, SHA-256 `ee7b8da9e381df27b9e3f7758a159ab2bdaa4dbaa910546cbbc47e0cb44e4f59`.
- All 12 saved questions match that file exactly at their recorded source indices (30, 263, 507, 509, 539, 756, 780, 851, 987, 1218, 1227, 1251).

So the Checkpoint 1 and 2 questions, answers, and results are valid. Only the recorded revision string and checksum were wrong.

### What was done

- The committed Checkpoint 1 and 2 evidence files were **not** edited. Results and manifests stay as recorded, and this note is the correction.
- The API's fallback manifest no longer hardcodes the revision; it reads it from the sample file.
- New samples pin a real commit (`740312add88f781978c0658806c59bc2815b9866`) and record the verified file checksum above.
