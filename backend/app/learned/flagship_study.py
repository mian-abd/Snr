"""The flagship extension (week of Nov 19): does adding flagship models to the pool pay off?

    uv run --project backend python -m app.learned.flagship_study --from-runs   # rebuild table
    uv run --project backend python -m app.learned.flagship_study               # from the table

The flagship models listed in ``data/registry/flagship-pool-2026-11-14.json`` answered the same
600 suite prompts and 300 fresh prompts as the Checkpoint 3 pool, on 2026-11-14, with the same
prompts, token limits, retry policy, and grading; a flagship that did not answer every prompt is
reported and left out. A second router is then fit with exactly the Checkpoint 3 recipe on the
pool plus the complete flagships: both classifier families compared on validation log
loss, presets tuned on the validation split with the same grids and floors, and the selected
model refit on train + validation. Nothing in the recipe was changed for the flagships.

The second router is evaluated once on the Checkpoint 3 test split and once on the fresh set,
next to the frozen router (which never saw the flagships), the fixed baselines, always using
the strongest flagship, per-task averages, and the hindsight oracle over every model. The
comparisons below were fixed in code before the flagships' results were read. The fresh set was
already used once, to evaluate the frozen router; it was not used to choose anything here.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from app.benchmarks.suite import RouterSplit, load_suite
from app.benchmarks.suite_runner import FINAL_PATH, FLAGSHIP_POOL_PATH, RUNS_DIR, SUITE_PATH
from app.config import REPOSITORY_ROOT
from app.domain.flagship import ExcludedFlagship, FlagshipRouter, FlagshipStudyReport
from app.domain.models import (
    ClassifierMetrics,
    ClassifierReport,
    EvaluationSet,
    LiveCatalogStatus,
    RoutingPriority,
)
from app.learned.evaluate import complete_prompts, routing_estimates, tune_weights
from app.learned.features import Cell, ModelHistory
from app.learned.final_eval import (
    CATALOG_PATH,
    CELLS_PATH,
    LEARNED_DIR,
    _cell_row,
    _sha256,
    evaluate_set,
    load_suites,
    summarize,
)
from app.learned.final_eval import (
    REPORT_PATH as FINAL_REPORT_PATH,
)
from app.learned.robustness import (
    Knowledge,
    RouterView,
    catalog_knowledge,
    retired_call_latency,
)
from app.learned.router import ROUTER_MODEL_PATH, LearnedRouter, load_router
from app.learned.train import (
    FIT_SPLITS,
    POOL_PATH,
    SELECTION_RULE,
    _metrics,
    build_dataset,
    export_router,
    fit_and_compare,
    matrix_summary,
    model_task_prior,
    select_family,
)
from app.registry.pool import PoolSnapshot, combine_pools, load_pool
from app.storage import atomic_write_json, atomic_write_jsonl, read_jsonl

RUN_IDS = {"cp3": "flagship-cp3", "final": "flagship-final"}
FLAGSHIP_CELLS_PATH = LEARNED_DIR / "flagship-cells.jsonl"
FLAGSHIP_ROUTER_PATH = LEARNED_DIR / "flagship-router-model.json"
FLAGSHIP_REPORT_PATH = LEARNED_DIR / "flagship-study.json"
TOP_FLAGSHIP = "fixed_top_flagship"
# Why a flagship was stopped before answering every prompt (the numbers are filled in).
STOPPED = {
    "grok-4.7": (
        "Stopped on 2026-11-14 after {scored} of {total} prompts. Its reasoning ignored the "
        "4,096-token answer limit on knowledge questions (one answer ran to 35,234 tokens and "
        "ten minutes), so finishing would have taken the flagship runs past their $25 budget."
    ),
}

# Fixed on 2026-11-14 before any flagship result was read. Each tuple: strategy, baseline,
# question. "learned" is the second router; "previous_router" is the frozen Checkpoint 3 router.
COMPARISONS: list[tuple[str, str, str]] = [
    ("learned:quality", "previous_router:quality",
     "Does the best-quality setting get more right with the flagships in the pool?"),
    ("learned:quality", TOP_FLAGSHIP,
     "Is the best-quality setting as accurate as always using the strongest flagship, for less?"),
    ("learned:cost", "previous_router:cost",
     "Does adding the flagships change the lowest-cost setting?"),
    ("learned:latency", "previous_router:latency",
     "Does adding the flagships change the fastest setting?"),
    ("learned:balanced", "previous_router:balanced",
     "Does the balanced setting do better with the flagships in the pool?"),
    ("learned:quality", "model_task_prior:quality",
     "With the flagships, do the prompt features add accuracy beyond per-task averages?"),
]


def build_flagship_cells() -> dict[str, Any]:
    """Collect the flagships' scored outcomes into one committed, text-free table."""
    rows: list[dict[str, Any]] = []
    spend: dict[str, float] = {}
    by_model: dict[str, float] = {}
    for suite, path in (("cp3", SUITE_PATH), ("final", FINAL_PATH)):
        items = {item.sample_id: item for item in load_suite(path)}
        run_dir = RUNS_DIR / RUN_IDS[suite]
        listed = {model.id for model in load_pool(FLAGSHIP_POOL_PATH).models}
        code_scores = {
            (score["model_id"], score["sample_id"]): bool(score["passed"])
            for score_path in run_dir.glob("*/code_scores.jsonl")
            for score in read_jsonl(score_path)
        }
        for results in sorted(run_dir.glob("*/results.jsonl")):
            for row in read_jsonl(results):
                item = items.get(row["sample_id"])
                if item is None or row["model_id"] not in listed:
                    continue  # only flagships belong in this table, whatever else ran here
                correct = row["correct"]
                if correct is None:
                    correct = code_scores.get((row["model_id"], row["sample_id"]))
                if correct is None:
                    continue  # code awaiting EvalPlus
                rows.append(_cell_row(suite, item, row, bool(correct)))
        for attempts in run_dir.glob("*/attempts.jsonl"):
            if attempts.parent.name not in listed:
                continue
            billed = float(sum(
                (
                    Decimal(str(row["result"].get("cost_usd") or "0"))
                    for row in read_jsonl(attempts)
                ),
                Decimal("0"),
            ))
            spend[suite] = spend.get(suite, 0.0) + billed
            by_model[attempts.parent.name] = by_model.get(attempts.parent.name, 0.0) + billed
    rows.sort(key=lambda row: (row["suite"], row["sample_id"], row["model_id"]))
    atomic_write_jsonl(FLAGSHIP_CELLS_PATH, rows)
    meta = {
        "rows": len(rows),
        "rows_by_suite": dict(Counter(row["suite"] for row in rows)),
        "rows_by_model": dict(Counter(row["model_id"] for row in rows)),
        "provider_billed_spend_usd": {key: round(value, 6) for key, value in spend.items()},
        "provider_billed_spend_by_model_usd": {
            key: round(value, 6) for key, value in sorted(by_model.items())
        },
        "cells_sha256": _sha256(FLAGSHIP_CELLS_PATH),
        "note": "Scored outcomes only: no prompts, responses, or request IDs. Same format as "
        "cells.jsonl; failed calls count as wrong.",
    }
    atomic_write_json(FLAGSHIP_CELLS_PATH.with_suffix(".meta.json"), meta)
    return meta


combined_pool = combine_pools


def strongest_flagship(cells: list[Cell], flagship_ids: list[str]) -> str:
    """Most right answers on the train and validation prompts; ties go to the cheaper one."""
    seen = [cell for cell in cells if cell.router_split in FIT_SPLITS]

    def key(model_id: str) -> tuple[int, float, str]:
        mine = [cell for cell in seen if cell.model_id == model_id]
        return (-sum(cell.correct for cell in mine), sum(cell.cost_usd for cell in mine), model_id)

    return min(flagship_ids, key=key)


def fit_router(
    cells: list[Cell], snapshot: PoolSnapshot
) -> tuple[LearnedRouter, FlagshipRouter]:
    """The Checkpoint 3 recipe (train.main), unchanged, on the combined pool."""
    items = {item.sample_id: item for item in load_suite(SUITE_PATH)}
    present = {cell.model_id for cell in cells}
    models = {model.id: model for model in snapshot.models if model.id in present}
    history = ModelHistory(cells)
    train = build_dataset(RouterSplit.TRAIN, cells, items, models, history)
    validation = build_dataset(RouterSplit.VALIDATION, cells, items, models, history)
    comparison = fit_and_compare(train, validation)
    selected = select_family(comparison)
    if selected != "logistic_regression":
        raise RuntimeError(
            f"Validation selected {selected}; only the linear router can be exported, so the "
            "recipe cannot be applied unchanged. Report this instead of switching families."
        )
    probability = comparison[selected]["_model"].predict_proba(validation.x)[:, 1]
    prior = model_task_prior(cells, validation, items)
    validation_prompts = complete_prompts(cells, RouterSplit.VALIDATION, sorted(models))
    train_only = frozenset({RouterSplit.TRAIN})
    tuned = tune_weights(
        validation_prompts, validation.probability(probability),
        routing_estimates(cells, train_only), sorted(models), cells, items,
    )
    fit_history = ModelHistory(cells, FIT_SPLITS)
    fit = build_dataset(FIT_SPLITS, cells, items, models, fit_history)
    artifact, _ = export_router(
        selected, comparison[selected]["best_params"], fit, fit_history, cells, tuned,
        snapshot, "cp3-full+flagship-cp3", models,
    )
    FLAGSHIP_ROUTER_PATH.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
    summary = FlagshipRouter(
        artifact_id=artifact.artifact_id,
        family=selected,
        params=comparison[selected]["best_params"],
        selection_rule=SELECTION_RULE,
        training_rows=len(fit.y),
        features=len(fit.names),
        classifiers={
            name: ClassifierReport.model_validate(
                {key: value for key, value in entry.items() if key != "_model"}
            )
            for name, entry in comparison.items()
        },
        reference_model_task_prior=ClassifierMetrics.model_validate(
            _metrics(validation.y, prior)
        ),
        validation_prompts=len(validation_prompts),
        weight_tuning=tuned,
    )
    return LearnedRouter(artifact, snapshot), summary


def build_report() -> FlagshipStudyReport:
    base = load_pool(POOL_PATH)
    listed = load_pool(FLAGSHIP_POOL_PATH)
    suites = load_suites((CELLS_PATH, FLAGSHIP_CELLS_PATH))
    meta = json.loads(FLAGSHIP_CELLS_PATH.with_suffix(".meta.json").read_text(encoding="utf-8"))
    by_model = meta["provider_billed_spend_by_model_usd"]
    total = sum(len(suite.items) for suite in suites.values())
    scored = Counter(cell.model_id for suite in suites.values() for cell in suite.cells)
    # Only a flagship with a scored answer to every prompt can join the pool; the rest are
    # reported with how far they got and what they cost.
    complete = [model for model in listed.models if scored[model.id] == total]
    excluded = [
        ExcludedFlagship(
            model_id=model.id,
            display_name=model.display_name,
            prompts_scored=scored[model.id],
            prompts_total=total,
            spend_usd=round(float(by_model.get(model.id, 0.0)), 6),
            reason=STOPPED.get(model.id, "Did not answer every prompt ({scored} of {total}).")
            .format(scored=scored[model.id], total=total),
        )
        for model in listed.models
        if model not in complete
    ]
    if not complete:
        raise RuntimeError(
            "No flagship has a scored answer to every prompt yet: finish the runs and score the "
            "code with app.benchmarks.code_scoring, then rebuild with --from-runs."
        )
    dropped = {item.model_id for item in excluded}
    for suite in suites.values():
        suite.cells = [cell for cell in suite.cells if cell.model_id not in dropped]
    flagships = listed.model_copy(update={"models": complete})
    pool = combined_pool(base, flagships)
    flagship_ids = [model.id for model in flagships.models]
    router, summary = fit_router(suites["cp3"].cells, pool)
    previous = load_router(ROUTER_MODEL_PATH, base)
    top = strongest_flagship(suites["cp3"].cells, flagship_ids)
    catalog = LiveCatalogStatus.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))
    drift = catalog_knowledge(catalog)
    retired_ms = retired_call_latency(suites["final"].cells)

    def extras(
        suite_name: str, knowledge: Knowledge
    ) -> Callable[[list[str]], dict[str, dict[str, str]]]:
        items = suites[suite_name].items

        def make(prompts: list[str]) -> dict[str, dict[str, str]]:
            view = RouterView(previous, items, prompts)
            picks = {
                f"previous_router:{priority.value}": {
                    sample: view.choose(sample, previous.artifact.weights[priority], knowledge)
                    for sample in prompts
                }
                for priority in RoutingPriority
            }
            picks[TOP_FLAGSHIP] = {sample: top for sample in prompts}
            return picks

        return make

    published = json.loads(FINAL_REPORT_PATH.read_text(encoding="utf-8"))

    def check_previous(evaluation: EvaluationSet) -> None:
        """The frozen router's picks here must reproduce its published final evaluation."""
        reference = next(
            item for item in published["evaluations"]
            if item["evaluation_id"] == evaluation.evaluation_id
        )
        for priority in RoutingPriority:
            mine = next(item for item in evaluation.strategies
                        if item.strategy_id == f"previous_router:{priority.value}")
            theirs = next(item for item in reference["strategies"]
                          if item["strategy_id"] == f"learned:{priority.value}")
            if (mine.correct, mine.selected_models) != (
                theirs["correct"], theirs["selected_models"]
            ) or abs(mine.total_cost_usd - theirs["total_cost_usd"]) > 1e-9:
                raise RuntimeError(
                    f"{evaluation.evaluation_id}: the frozen router's {priority.value} picks no "
                    "longer match final-evaluation.json"
                )

    cp3, *_ = evaluate_set(
        "cp3_test",
        "Original test split",
        "The 120 held-out test prompts of the 600-prompt suite, answered by the Checkpoint 3 "
        "pool in late October and by the flagships on 2026-11-14.",
        router, suites["cp3"], RouterSplit.TEST, Knowledge(), COMPARISONS, retired_ms,
        extra_picks=extras("cp3", Knowledge()),
    )
    check_previous(cp3)
    final, *_ = evaluate_set(
        "final",
        "Fresh prompts",
        "The 300 fresh prompts, answered by the Checkpoint 3 pool on 2026-11-13 and 14 and by "
        "the flagships on 2026-11-14. Both routers apply the live catalog of 2026-11-13, so "
        "Mercury 3 (retired) is excluded.",
        router, suites["final"], RouterSplit.FINAL, drift, COMPARISONS, retired_ms,
        extra_picks=extras("final", drift),
    )
    check_previous(final)
    names = {model.id: model.display_name for model in flagships.models}
    return FlagshipStudyReport(
        title="With flagship models",
        question=f"Does adding {len(flagship_ids)} flagship models to the pool pay off?",
        flagship_snapshot_id=listed.snapshot_id,
        flagships=flagships.models,
        excluded_flagships=excluded,
        strongest_flagship_id=top,
        router=summary,
        protocol=[
            f"The flagships ({', '.join(names.values())}) answered the 600 suite prompts and the "
            "300 fresh prompts on 2026-11-14 through OpenRouter, each pinned to its maker's own "
            "standard tier, with the same prompts, token limits, retry policy, and grading as "
            "the Checkpoint 3 pool.",
            *(f"{item.display_name} is left out: {item.reason}" for item in excluded),
            f"The second router uses the Checkpoint 3 recipe unchanged on all "
            f"{len(router.pool_ids)} models: "
            "classifier family and regularization chosen on validation log loss, presets tuned "
            "on the validation split with the same grids and accuracy floors, then refit on "
            "train + validation.",
            f"The strongest flagship, {names[top]}, is the one with the most right answers on "
            "the train and validation prompts, fixed before the test and fresh results were read.",
            "The paired comparisons were fixed in code before the flagships' results were read; "
            "p-values are Holm-adjusted within each evaluation. Intervals are 95% bootstrap "
            "intervals over prompts (10,000 resamples, fixed seed).",
            "The fresh prompts were already used once, to evaluate the frozen router. Nothing in "
            "this extension was chosen on them; they are read once more here.",
        ],
        evaluations=[cp3, final],
        suite_matrix=matrix_summary(
            suites["cp3"].cells, {model.id: model for model in pool.models}
        ),
        spend_usd={key: float(value) for key, value in meta["provider_billed_spend_usd"].items()},
        spend_by_model_usd={key: float(value) for key, value in by_model.items()},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-runs", action="store_true",
                        help="Rebuild data/learned/flagship-cells.jsonl from the raw local runs")
    args = parser.parse_args()
    if args.from_runs:
        meta = build_flagship_cells()
        print(f"flagship cells: {meta['rows_by_model']}, spend {meta['provider_billed_spend_usd']}")
    report = build_report()
    FLAGSHIP_REPORT_PATH.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    router = report.router
    for name, classifier in router.classifiers.items():
        print(f"{name}: val log loss {classifier.validation.log_loss:.4f} "
              f"{classifier.best_params}")
    print(f"per-task reference: val log loss {router.reference_model_task_prior.log_loss:.4f}")
    for result in router.weight_tuning:
        print(f"tuned {result.priority.value}: {result.weights.model_dump()} -> "
              f"{result.validation_correct}/{router.validation_prompts}")
    print(f"strongest flagship: {report.strongest_flagship_id}")
    for evaluation in report.evaluations:
        print(f"{evaluation.title}: {evaluation.prompts} prompts, "
              f"log loss {evaluation.classifier.log_loss:.4f} "
              f"(table {evaluation.reference_model_task_prior.log_loss:.4f})")
        summarize(evaluation.strategies + evaluation.oracle, evaluation.evaluation_id)
        for comparison in evaluation.comparisons:
            print(f"  {comparison.strategy_id} vs {comparison.baseline_id}: "
                  f"{comparison.accuracy_difference:+.3f} Holm p={comparison.holm_p:.3f}, "
                  f"cost ratio {comparison.cost_ratio}")
    print(f"wrote {FLAGSHIP_REPORT_PATH.relative_to(REPOSITORY_ROOT)} and "
          f"{FLAGSHIP_ROUTER_PATH.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
