# Data dictionary

This describes the committed data files under `data/benchmarks/` and `data/learned/`, and the seven export tables served by `GET /api/v1/learned/export/{table}` and `python -m app.learned.export` (`backend/app/learned/export.py`).

`uv run --project backend python -m app.learned.validate` checks the cell tables against their metadata and suite files, recomputes the reports' model matrices from the cells, and scans `data/learned/` and `data/registry/` for anything that looks like a key. It runs in CI after the tests.

## Conventions

- **Cost** is in US dollars, as billed by the provider for the call. Free and local models cost $0.
- **Latency** is in milliseconds unless the column says otherwise: wall-clock time of one call, measured by the client from sending the request to receiving the whole response. A failed call has the latency of its failure.
- **Accuracy** is a fraction from 0 to 1 (right answers divided by prompts). **Correct** is a count, or a boolean on a single call.
- A **failed call** (any status other than `success`) counts as wrong.
- **Checksums** are SHA-256 of the file with CRLF line endings read as LF, so a Windows checkout gives the same value as git.
- `null` means the value does not apply or was not reported.

### Identifiers

| Name | Values |
| --- | --- |
| `suite` | `cp3`: the 600-prompt suite (`cp3_suite.jsonl`). `final`: the 300 fresh prompts (`final_heldout.jsonl`). |
| `evaluation` | `cp3_test`: the 120 test-split prompts of the `cp3` suite. `final`: all 300 fresh prompts. |
| `benchmark` | `gsm8k`, `mmlu_pro`, `humaneval_plus`, `mbpp_plus`. |
| `task_group` | `math` (GSM8K), `qa` (MMLU-Pro), `code` (HumanEval+ and MBPP+). |
| `router_split` | `train`, `validation`, `test` (the `cp3` suite, 60/20/20 per benchmark), `final` (fresh prompts). |
| `model_id` | A pool model, as listed in `data/registry/cp3-pool-2026-10-27.json` or `data/registry/flagship-pool-2026-11-14.json`. |
| Priority | `quality` (best quality), `cost` (lowest cost), `latency` (fastest), `balanced`. Each is a preset of weights for quality, cost, latency, and reliability. |

Strategy ids, in the reports and export tables:

| Strategy | Meaning |
| --- | --- |
| `fixed_cheapest` | Always the cheapest paid model (`gemma-4-26b`). |
| `fixed_strongest` | Always the strongest model (`gemini-4-argon`). |
| `rule_balanced` | The rule-based router. `rule_balanced_no_catalog`: the same, ignoring the live catalog. |
| `learned:<priority>` | The frozen learned router with that priority's preset. On the fresh prompts it applies the live catalog of 2026-11-13. In robustness results: the router told about the change. |
| `learned_no_catalog:<priority>` | The learned router without the live catalog (it still routes to the retired Mercury 3). |
| `learned_frozen:<priority>` | Robustness only: the learned router keeping its trained estimates after the change. |
| `model_task_prior:<priority>` | The same scoring with each model's per-task success rate in place of the classifier. |
| `oracle:<priority>` | Hindsight: for each prompt, the model that scores best under the preset's weights given what every model actually did. |
| `previous_router:<priority>` | Flagship study only: the frozen router, next to the second router (`learned:<priority>` there). |
| `fixed_top_flagship` | Flagship study only: always the strongest flagship. |

## data/benchmarks

### cp3_suite.jsonl and final_heldout.jsonl

One prompt per line. `cp3_suite.jsonl` has 600 prompts (GSM8K 200, MMLU-Pro 200, HumanEval+ 100, MBPP+ 100); `final_heldout.jsonl` has 300 (100, 100, 50, 50), drawn after the router was frozen and sharing no prompt with the suite or with Checkpoint 1. Code test suites are not stored; they stay in the pinned source releases.

| Column | Meaning | Units |
| --- | --- | --- |
| `sample_id` | Stable prompt id, `<benchmark>-<source split>-<index>` or `<benchmark>-<index>`. | text |
| `benchmark` | Source benchmark. | see Identifiers |
| `task_group` | Task group of the benchmark. | see Identifiers |
| `dataset` | Source dataset, for example `openai/gsm8k`. | text |
| `configuration` | Dataset configuration (`main` for GSM8K), else `null`. | text |
| `source_split` | Split of the source dataset the prompt was drawn from. | text |
| `revision` | Pinned dataset commit or release tag. | text |
| `source_id` | The prompt's id or row index in the source. | text |
| `category` | MMLU-Pro subject, else `null`. | text |
| `question` | The prompt text: the problem, question, or function stub. | text |
| `options` | MMLU-Pro answer options, in order (A, B, ...); empty otherwise. | list of text |
| `expected_answer` | Reference answer: the number for GSM8K, the option letter for MMLU-Pro; `null` for code. | text |
| `entry_point` | Function the code tests call; `null` for other tasks. | text |
| `router_split` | `train`, `validation`, or `test` in the suite; `final` in the fresh set. | see Identifiers |

### cp3_suite.meta.json and final_heldout.meta.json

| Key | Meaning |
| --- | --- |
| `suite` | Suite name (`cp3`, `final-heldout`). |
| `seed` | Random seed of the draw (and, for `cp3`, of the split). |
| `counts` | Prompts per benchmark and router split. |
| `split_fractions` | `cp3` only: train, validation, and test shares. |
| `sources` | Per benchmark: `dataset`, `kind` (`hf` or `release`), `file` or `url`, `revision`, `license`, `sha256` of the downloaded source file, `source_rows` (rows available), `sampled` (rows drawn), `split`, and for the fresh set `excluded_as_used` (source rows left out because the suite or Checkpoint 1 used them). |
| `excluded` | Rows left out before drawing: the 12 Checkpoint 1 GSM8K indices; for the fresh set also `cp3_suite_sha256`, the suite whose prompts were excluded. |
| `suite_sha256`, `final_sha256` | Checksum of the `.jsonl` file. |
| `drawn_after` | Fresh set only: what had been fixed before it was drawn. |

### gsm8k_checkpoint1.jsonl and gsm8k_checkpoint1.meta.json

The 12 GSM8K test questions of the Checkpoint 1 pilot. Columns: `dataset`, `configuration`, `revision`, `split` (as above); `source_index` (row in the source split); `sample_id`; `question`; `canonical_answer` (the dataset's worked solution); `expected_answer` (its final number); `selection_seed`. The meta file records the dataset, revision, `source_file_sha256` (checksum of the downloaded source file), `selection_seed`, `source_indices`, and `sample_size`.

## data/learned

### cells.jsonl and flagship-cells.jsonl

One scored call per line: one model's outcome on one prompt. Sorted by `suite`, `sample_id`, `model_id`; each (suite, sample_id, model_id) appears once. `cells.jsonl` holds the 9 pool models on all 900 prompts (8,100 rows); `flagship-cells.jsonl` holds the flagship models (3,075 rows: three complete flagships, and the 375 prompts Grok 4.7 answered before it was stopped). No prompt text, response text, or request id is stored. The `cells` export table serves `cells.jsonl`.

| Column | Meaning | Units |
| --- | --- | --- |
| `suite` | Prompt set. | `cp3` or `final` |
| `sample_id` | Prompt id; joins to the suite file. | text |
| `benchmark` | Benchmark of the prompt. | see Identifiers |
| `task_group` | Task group of the prompt. | see Identifiers |
| `router_split` | Split of the prompt. | see Identifiers |
| `model_id` | Model that answered. | text |
| `status` | Outcome of the scored call: `success`, `provider_error`, `timeout`, `rate_limited`, `invalid_response`, or `model_mismatch`. A retryable failure is retried once; the second attempt is the scored one. | text |
| `correct` | Whether the answer was graded right: extracted number for GSM8K, option letter for MMLU-Pro, the EvalPlus tests for code. Always `false` for a failed call. | boolean |
| `latency_ms` | Wall-clock time of the scored call. | ms |
| `cost_usd` | Billed cost of the scored call. A first attempt that was retried is not included here; it is in the meta's spend. | USD |
| `completion_tokens` | Output tokens the provider reported for the scored call; `null` if none were reported. | tokens |

`cells.meta.json` and `flagship-cells.meta.json`:

| Key | Meaning | Units |
| --- | --- | --- |
| `rows` | Rows in the table. | count |
| `rows_by_suite` | Rows per suite. | count |
| `rows_by_model` | Flagship table only: rows per model. | count |
| `provider_billed_spend_usd` | Everything billed per suite, every attempt included. | USD |
| `provider_billed_spend_by_model_usd` | Flagship table only: the same per model, both suites together. | USD |
| `cells_sha256` | Checksum of the `.jsonl` file. | hex |
| `note` | What the table holds. | text |

### final-decisions.jsonl

Every strategy's choice on every prompt of both evaluations (15 strategies on `cp3_test`, 20 on `final`; 7,800 rows). The outcome is the chosen model's stored call from the cell table. The `decisions` export table serves this file.

| Column | Meaning | Units |
| --- | --- | --- |
| `evaluation` | Evaluation. | `cp3_test` or `final` |
| `sample_id` | Prompt id. | text |
| `benchmark` | Benchmark of the prompt. | see Identifiers |
| `task_group` | Task group of the prompt. | see Identifiers |
| `strategy` | Strategy id. | see Identifiers |
| `model_id` | Model the strategy chose. | text |
| `correct` | Whether that model's answer was right. | boolean |
| `served` | Whether that model's call succeeded. | boolean |
| `cost_usd` | Billed cost of that call. | USD |
| `latency_ms` | Wall-clock time of that call. | ms |

### cp3-router-model.json and flagship-router-model.json

The exported linear routers (`RouterArtifact` in `backend/app/learned/router.py`). `cp3-router-model.json` is the frozen router evaluated in `final-evaluation.json`; its checksum is the report's `artifact_sha256`. `flagship-router-model.json` is the second router of the flagship study, fit with the same recipe on the pool plus the flagships.

| Key | Meaning |
| --- | --- |
| `artifact_id`, `run_id`, `pool_snapshot_id` | Names of the router, the training run, and the model pool snapshot. |
| `family`, `params`, `selection_rule` | Classifier family (`logistic_regression`), its regularization, and why it was chosen. |
| `trained_on_splits`, `training_rows` | Splits the final fit used and its number of (prompt, model) rows. |
| `model_ids`, `features` | The models it routes over and the feature names. |
| `scaler_mean`, `scaler_scale`, `coefficients`, `intercept` | Feature standardization and the logistic-regression weights; the predicted probability that a model answers a prompt right. |
| `history` | Per-model success counts, latency, and output tokens on the training splits, used as features. |
| `estimates` | Per model and task group: `expected_cost_usd` (mean billed cost per call, USD), `expected_latency_ms` (median latency of served calls, ms), `failure_rate` (share of failed calls, 0 to 1). |
| `weights` | The tuned preset per priority: weights for `quality`, `cost`, `latency`, and `reliability`. |

### cp3-full-router-comparison.json

The Checkpoint 3 report (`LearnedRouterReport` in `backend/app/domain/models.py`): the 600 × 9 model matrix (`matrix`), the two classifier families compared on validation log loss (`classifiers`), the selected family, validation replays and weight tuning (`strategies`, `weight_tuning`), and the single read of the 120-prompt test split (`heldout`, with each strategy's `prompts`, `correct`, `accuracy`, `total_cost_usd` in USD, `cost_per_correct_usd`, `median_latency_ms` and `p95_latency_ms` in ms, `selected_models`, and per-task results in `by_task`). `python -m app.learned.plots` draws the `cp3-heldout-*` figures from it.

### final-evaluation.json

The final evaluation of the frozen router (`FinalEvaluationReport`).

| Key | Meaning |
| --- | --- |
| `artifact_id`, `artifact_sha256` | The router evaluated and the checksum of `cp3-router-model.json`. |
| `final_set_sha256` | Checksum of `final_heldout.jsonl`. |
| `pool_snapshot_id`, `catalog` | The pool snapshot, and the live catalog saved on 2026-11-13 (retired models and live prices). |
| `protocol` | What was fixed before the results were read, in sentences. |
| `evaluations` | One entry per evaluation (`cp3_test`, `final`): `prompts`, `prompts_by_task`, `models`, `catalog_applied`, classifier metrics on those prompts (`log_loss`, `brier`, `roc_auc`, `accuracy_at_0_5`, `rows`), `matrix` (per model: `prompts`, `correct`, `prompts_by_task`, `correct_by_task`, `failed_calls`, `median_latency_ms` over served calls, `cost_usd`), `strategies` and `oracle` (as in the `strategies` export table), `uncertainty`, `comparisons`, and `routing_errors`. |
| `robustness` | Per evaluation: the scenarios and the priority sweep (the `robustness` and `sweep` export tables), with notes. |
| `spend_usd` | Billed cost of the fresh-set run, every attempt included, USD. |

The validator recomputes each `matrix` from `cells.jsonl`: `cp3_test` over the suite's test split, `final` over every fresh prompt, for the models in `models`.

### flagship-study.json

The flagship extension (`FlagshipStudyReport` in `backend/app/domain/flagship.py`): `flagships` (the flagships that answered every prompt, with prices and hosts), `excluded_flagships` (with prompts scored, spend in USD, and the reason), `strongest_flagship_id`, `router` (the second router's selection, classifier metrics, and tuned presets), `protocol`, `evaluations` (same shape as in `final-evaluation.json`, over the pool plus the complete flagships), `suite_matrix` (every model over the 600 suite prompts), `spend_usd` (billed per prompt set, USD), and `spend_by_model_usd` (billed per flagship, USD). It is computed from `cells.jsonl` and `flagship-cells.jsonl`; a report with a `cell_tables` list is checked against exactly those tables instead.

## Export tables

`GET /api/v1/learned/export/{table}?format=csv|json` and `python -m app.learned.export TABLE --format csv|json --out FILE`. Every table is built from committed files only and holds no response text or keys. In CSV, `selected_models` is written as `model x count; model x count`, most chosen first; an empty cell is `null`.

### strategies

Every strategy and oracle on both evaluations (one row per evaluation and strategy). Intervals are 95% percentile-bootstrap intervals over prompts (10,000 resamples, fixed seed).

| Column | Meaning | Units |
| --- | --- | --- |
| `evaluation` | Evaluation. | `cp3_test` or `final` |
| `strategy` | Strategy id. | see Identifiers |
| `prompts` | Prompts evaluated. | count |
| `correct` | Right answers. | count |
| `accuracy` | `correct / prompts`, rounded to 6 decimals. | fraction |
| `accuracy_ci_low`, `accuracy_ci_high` | 95% interval for accuracy. | fraction |
| `total_cost_usd` | Billed cost of the chosen calls over all prompts. | USD |
| `total_cost_usd_ci_low`, `total_cost_usd_ci_high` | 95% interval for total cost. | USD |
| `cost_per_correct_usd` | `total_cost_usd / correct`; `null` if nothing was right. | USD |
| `median_latency_ms` | Median latency of the chosen calls, failed calls included. | ms |
| `median_latency_ms_ci_low`, `median_latency_ms_ci_high` | 95% interval for the median latency. | ms |
| `p95_latency_ms` | 95th-percentile latency of the chosen calls. | ms |
| `selected_models` | How many prompts went to each model. | model x count |
| `math_correct`, `qa_correct`, `code_correct` | Right answers in the task group. | count |
| `math_prompts`, `qa_prompts`, `code_prompts` | Prompts in the task group. | count |
| `math_cost_usd`, `qa_cost_usd`, `code_cost_usd` | Billed cost in the task group. | USD |

### comparisons

The paired comparisons fixed in code before the results were read (one row per evaluation and comparison). Differences are strategy minus baseline on the same prompts.

| Column | Meaning | Units |
| --- | --- | --- |
| `evaluation` | Evaluation. | `cp3_test` or `final` |
| `strategy_id`, `baseline_id` | The two strategies compared. | see Identifiers |
| `question` | The question the comparison answers. | text |
| `prompts` | Prompts compared. | count |
| `correct`, `baseline_correct` | Right answers of each. | count |
| `only_strategy_correct`, `only_baseline_correct` | Prompts only one of the two got right (the discordant pairs). | count |
| `accuracy_difference` | Accuracy of the strategy minus the baseline's. | fraction |
| `accuracy_difference_ci_low`, `accuracy_difference_ci_high` | 95% bootstrap interval for it. | fraction |
| `mcnemar_p` | Exact two-sided McNemar test on the discordant pairs. | probability |
| `holm_p` | `mcnemar_p` after Holm adjustment within the evaluation. | probability |
| `cost_difference_usd` | Total billed cost of the strategy minus the baseline's. | USD |
| `cost_difference_ci_low`, `cost_difference_ci_high` | 95% bootstrap interval for it. | USD |
| `cost_ratio` | Strategy total cost divided by the baseline's; `null` if the baseline cost $0. | ratio |
| `cost_ratio_ci_low`, `cost_ratio_ci_high` | 95% bootstrap interval for the ratio, over resamples where the baseline cost more than $0. | ratio |
| `median_latency_difference_ms` | Median latency of the strategy minus the baseline's. | ms |
| `median_latency_difference_ci_low`, `median_latency_difference_ci_high` | 95% bootstrap interval for it. | ms |

### errors

Routing errors and the oracle gap for each learned preset, over all prompts (`task_group` = `all`) and per task group. "Cheaper" and "costlier" use the router's own expected cost for the prompt's task group, at the live price where the catalog gave one; retired models are not counted as alternatives.

| Column | Meaning | Units |
| --- | --- | --- |
| `evaluation` | Evaluation. | `cp3_test` or `final` |
| `strategy` | Learned preset (`learned:<priority>`). | see Identifiers |
| `task_group` | `all`, `math`, `qa`, or `code`. | text |
| `prompts` | Prompts in the group. | count |
| `correct`, `wrong` | Right and wrong answers of the strategy. | count |
| `unavoidable` | Wrong, and no model was right. | count |
| `under_routed` | Wrong, while a model the router expected to cost more was right. | count |
| `over_routed` | Right, while a model the router expected to cost less was also right. | count |
| `over_routed_dominated` | Over-routed, and such a cheaper model was also no costlier and no slower on the actual call. | count |
| `over_routing_extra_cost_usd` | Over the over-routed prompts: billed cost of the chosen call minus the cheapest call that was right. | USD |
| `total_cost_usd` | Billed cost of the strategy in the group. | USD |
| `oracle_correct`, `oracle_cost_usd` | Right answers and billed cost of the oracle for the same priority. | count, USD |
| `regret_correct` | `oracle_correct - correct`. | count |

### robustness

Every robustness scenario and strategy (one row per evaluation, scenario, and strategy). A scenario replays the stored calls with costs or latencies rescaled, calls failed, or models made unavailable; on the fresh prompts the observed drift is already in the stored calls, and hypothetical changes come on top of it. See `docs/checkpoint-4-progress.md`, "Robustness tests".

| Column | Meaning | Units |
| --- | --- | --- |
| `evaluation` | Evaluation. | `cp3_test` or `final` |
| `scenario` | Scenario id, for example `observed_drift`, `gemma_price_x30`, `free_outage_50`. | text |
| `title` | Scenario title as shown in the figures. | text |
| `condition` | What changes: `availability`, `price`, `latency`, or `reliability` (`none` for no change). | text |
| `observed` | `true` for the change that really happened on the providers (2026-11-12 and 13), `false` for a what-if. | boolean |
| `strategy` | Strategy id; `learned:<priority>` is told about the change, `learned_frozen:<priority>` keeps its old estimates. | see Identifiers |
| `prompts` | Prompts in the evaluation. | count |
| `correct` | Right answers under the scenario. | count |
| `accuracy` | `correct / prompts`. | fraction |
| `total_cost_usd` | Billed cost under the scenario (rescaled prices; an injected failure costs $0). | USD |
| `median_latency_ms` | Median latency under the scenario (an injected failure takes 2,000 ms). | ms |
| `changed_decisions` | Prompts where the strategy chose a different model than with nothing changed. | count |
| `selected_models` | How many prompts went to each model. | model x count |

### sweep

The learned router with quality weight 1 and one other weight varied from 0 to 5, the rest 0 (one row per evaluation, axis, and weight).

| Column | Meaning | Units |
| --- | --- | --- |
| `evaluation` | Evaluation. | `cp3_test` or `final` |
| `axis` | The weight varied. | `cost` or `latency` |
| `weight` | Its value. | weight (unitless) |
| `correct` | Right answers. | count |
| `accuracy` | `correct / prompts`. | fraction |
| `total_cost_usd` | Billed cost over all prompts. | USD |
| `median_latency_ms` | Median latency of the chosen calls. | ms |
| `selected_models` | How many prompts went to each model. | model x count |

### decisions

The rows of `data/learned/final-decisions.jsonl`; columns as described there.

### cells

The rows of `data/learned/cells.jsonl` (the 9 pool models only; the flagships are in `flagship-cells.jsonl`); columns as described there.
