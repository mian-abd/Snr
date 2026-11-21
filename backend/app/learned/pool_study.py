"""Pool studies: refit the Checkpoint 3 recipe on a widened pool and compare it with the frozen one.

    uv run --project backend python -m app.learned.pool_study --study flagship --from-runs
    uv run --project backend python -m app.learned.pool_study --study wide --from-runs
    uv run --project backend python -m app.learned.pool_study --study wide   # committed tables

The added models (``app.learned.studies``) answered the same 600 suite prompts and 300 fresh
prompts as the Checkpoint 3 pool, with the same prompts, token limits, retry policy, and grading;
a listed model that did not answer every prompt is reported and left out. The study's router is
then fit with exactly the Checkpoint 3 recipe: both classifier families compared on validation
log loss, presets tuned on the validation split with the same grids and floors, and the selected
model refit on train + validation. Nothing in the recipe changes with the pool.

The router is evaluated once on the Checkpoint 3 test split and once on the fresh set, next to
the frozen router (which never saw the added models), any earlier study's router, the fixed
baselines, always using the strongest added model, per-task averages, and the hindsight oracle
over every model. Each study's comparisons were fixed in code before its results were read.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.benchmarks.suite import RouterSplit, load_suite
from app.benchmarks.suite_runner import FINAL_PATH, RUNS_DIR, SUITE_PATH
from app.config import REPOSITORY_ROOT
from app.domain.models import (
    ClassifierMetrics,
    ClassifierReport,
    EvaluationSet,
    LiveCatalogStatus,
    RoutingPriority,
)
from app.domain.study import ExcludedModel, PoolStudyReport, StudyRouter
from app.learned.evaluate import complete_prompts, routing_estimates, tune_weights
from app.learned.features import Cell, ModelHistory
from app.learned.final_eval import (
    CATALOG_PATH,
    CELLS_PATH,
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
from app.learned.studies import ADDED_POOLS, STUDIES, TOP_ADDED, AddedPool, StudySpec
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


def build_cells(pool: AddedPool) -> dict[str, Any]:
    """Collect an added pool's scored outcomes into one committed, text-free table."""
    listed = {model.id for model in load_pool(pool.registry).models}
    rows: list[dict[str, Any]] = []
    spend: dict[str, float] = {}
    by_model: dict[str, float] = {}
    for suite, path in (("cp3", SUITE_PATH), ("final", FINAL_PATH)):
        items = {item.sample_id: item for item in load_suite(path)}
        run_dir = RUNS_DIR / pool.run_ids[suite]
        code_scores = {
            (score["model_id"], score["sample_id"]): bool(score["passed"])
            for score_path in run_dir.glob("*/code_scores.jsonl")
            for score in read_jsonl(score_path)
        }
        for results in sorted(run_dir.glob("*/results.jsonl")):
            for row in read_jsonl(results):
                item = items.get(row["sample_id"])
                if item is None or row["model_id"] not in listed:
                    continue  # only this pool's models belong here, whatever else ran
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
    atomic_write_jsonl(pool.cells_path, rows)
    meta = {
        "rows": len(rows),
        "rows_by_suite": dict(Counter(row["suite"] for row in rows)),
        "rows_by_model": dict(Counter(row["model_id"] for row in rows)),
        "provider_billed_spend_usd": {key: round(value, 6) for key, value in spend.items()},
        "provider_billed_spend_by_model_usd": {
            key: round(value, 6) for key, value in sorted(by_model.items())
        },
        "cells_sha256": _sha256(pool.cells_path),
        "note": "Scored outcomes only: no prompts, responses, or request IDs. Same format as "
        "cells.jsonl; failed calls count as wrong.",
    }
    atomic_write_json(pool.cells_path.with_suffix(".meta.json"), meta)
    return meta


def strongest_added(cells: list[Cell], model_ids: list[str]) -> str:
    """Most right answers on the train and validation prompts; ties go to the cheaper one."""
    seen = [cell for cell in cells if cell.router_split in FIT_SPLITS]

    def key(model_id: str) -> tuple[int, float, str]:
        mine = [cell for cell in seen if cell.model_id == model_id]
        return (-sum(cell.correct for cell in mine), sum(cell.cost_usd for cell in mine), model_id)

    return min(model_ids, key=key)


def fit_router(
    cells: list[Cell], snapshot: PoolSnapshot, run_label: str, out: Path
) -> tuple[LearnedRouter, StudyRouter]:
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
        snapshot, run_label, models,
    )
    out.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
    summary = StudyRouter(
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


def _check_reproduces(
    evaluation: EvaluationSet, prefix: str, published: dict[str, Any], source: str
) -> None:
    """A baseline router's picks here must reproduce its own published results exactly."""
    reference = next(
        item for item in published["evaluations"]
        if item["evaluation_id"] == evaluation.evaluation_id
    )
    for priority in RoutingPriority:
        mine = next(item for item in evaluation.strategies
                    if item.strategy_id == f"{prefix}:{priority.value}")
        theirs = next(item for item in reference["strategies"]
                      if item["strategy_id"] == f"learned:{priority.value}")
        if (mine.correct, mine.selected_models) != (
            theirs["correct"], theirs["selected_models"]
        ) or abs(mine.total_cost_usd - theirs["total_cost_usd"]) > 1e-9:
            raise RuntimeError(
                f"{evaluation.evaluation_id}: {prefix} {priority.value} picks no longer match "
                f"{source}"
            )


def _list_and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def build_report(spec: StudySpec) -> PoolStudyReport:
    base = load_pool(POOL_PATH)
    pools = spec.added
    listed = {pool.name: load_pool(pool.registry) for pool in pools}
    tables = (CELLS_PATH, *(pool.cells_path for pool in pools))
    suites = load_suites(tables)
    metas = {
        pool.name: json.loads(pool.cells_path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        for pool in pools
    }
    by_model = {
        key: float(value)
        for meta in metas.values()
        for key, value in meta["provider_billed_spend_by_model_usd"].items()
    }
    total = sum(len(suite.items) for suite in suites.values())
    scored = Counter(cell.model_id for suite in suites.values() for cell in suite.cells)
    # Only a model with a scored answer to every prompt can join the pool; the rest are
    # reported with how far they got and what they cost.
    complete: dict[str, list[Any]] = {
        pool.name: [model for model in listed[pool.name].models if scored[model.id] == total]
        for pool in pools
    }
    excluded = [
        ExcludedModel(
            model_id=model.id,
            display_name=model.display_name,
            prompts_scored=scored[model.id],
            prompts_total=total,
            spend_usd=round(by_model.get(model.id, 0.0), 6),
            reason=pool.stopped.get(model.id, "Did not answer every prompt ({scored} of {total}).")
            .format(scored=scored[model.id], total=total),
        )
        for pool in pools
        for model in listed[pool.name].models
        if model not in complete[pool.name]
    ]
    added = [model for pool in pools for model in complete[pool.name]]
    if not added:
        raise RuntimeError(
            "No added model has a scored answer to every prompt yet: finish the runs and score "
            "the code with app.benchmarks.code_scoring, then rebuild with --from-runs."
        )
    dropped = {item.model_id for item in excluded}
    for suite in suites.values():
        suite.cells = [cell for cell in suite.cells if cell.model_id not in dropped]
    pool_snapshot = combine_pools(
        base, *(listed[pool.name].model_copy(update={"models": complete[pool.name]})
                for pool in pools)
    )
    added_ids = [model.id for model in added]
    run_label = "+".join(["cp3-full", *(pool.run_ids["cp3"] for pool in pools)])
    router, summary = fit_router(suites["cp3"].cells, pool_snapshot, run_label, spec.router_path)
    previous = load_router(ROUTER_MODEL_PATH, base)
    baselines: dict[str, LearnedRouter] = {}
    for study_id in spec.baseline_studies:
        other = STUDIES[study_id]
        baselines[study_id] = load_router(
            other.router_path,
            combine_pools(base, *(load_pool(pool.registry) for pool in other.added)),
        )
    top = strongest_added(suites["cp3"].cells, added_ids)
    catalog = LiveCatalogStatus.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))
    drift = catalog_knowledge(catalog)
    retired_ms = retired_call_latency(suites["final"].cells)

    def extras(
        suite_name: str, knowledge: Knowledge
    ) -> Callable[[list[str]], dict[str, dict[str, str]]]:
        items = suites[suite_name].items

        def make(prompts: list[str]) -> dict[str, dict[str, str]]:
            picks: dict[str, dict[str, str]] = {}
            for prefix, other in (("previous_router", previous),
                                  *((f"{key}_router", value) for key, value in baselines.items())):
                view = RouterView(other, items, prompts)
                for priority in RoutingPriority:
                    picks[f"{prefix}:{priority.value}"] = {
                        sample: view.choose(sample, other.artifact.weights[priority], knowledge)
                        for sample in prompts
                    }
            picks[TOP_ADDED] = {sample: top for sample in prompts}
            return picks

        return make

    published = json.loads(FINAL_REPORT_PATH.read_text(encoding="utf-8"))
    earlier = {
        study_id: json.loads(STUDIES[study_id].report_path.read_text(encoding="utf-8"))
        for study_id in spec.baseline_studies
    }
    comparisons = list(spec.comparisons)
    dates = _list_and([f"the {pool.plural} on {pool.answered_on}" for pool in pools])
    routers_word = "Both routers" if not spec.baseline_studies else "Every router"
    evaluations = []
    for evaluation_id, title, split, knowledge, description in (
        ("cp3_test", "Original test split", RouterSplit.TEST, Knowledge(),
         "The 120 held-out test prompts of the 600-prompt suite, answered by the Checkpoint 3 "
         f"pool in late October and by {dates}."),
        ("final", "Fresh prompts", RouterSplit.FINAL, drift,
         "The 300 fresh prompts, answered by the Checkpoint 3 pool on 2026-11-13 and 14 and by "
         f"{dates}. {routers_word} apply the live catalog of 2026-11-13, so Mercury 3 (retired) "
         "is excluded."),
    ):
        suite = suites["cp3" if evaluation_id == "cp3_test" else "final"]
        evaluation, *_ = evaluate_set(
            evaluation_id, title, description, router, suite, split, knowledge, comparisons,
            retired_ms, extra_picks=extras(suite.name, knowledge),
        )
        _check_reproduces(evaluation, "previous_router", published, "final-evaluation.json")
        for study_id, report in earlier.items():
            _check_reproduces(evaluation, f"{study_id}_router", report,
                              STUDIES[study_id].report_path.name)
        evaluations.append(evaluation)

    names = {model.id: model.display_name for model in added}
    single = "flagship" if spec.pools == ("flagship",) else "added model"
    intro = [
        f"The {pool.plural} ({', '.join(model.display_name for model in complete[pool.name])}) "
        f"answered the 600 suite prompts and the 300 fresh prompts on {pool.answered_on} "
        "through OpenRouter, each pinned to one host (its maker's own where there is one), "
        "with the same prompts, token limits, retry policy, and grading as the Checkpoint 3 pool."
        for pool in pools
    ]
    if spec.pools == ("flagship",):
        intro = [
            f"The flagships ({', '.join(names.values())}) answered the 600 suite prompts and the "
            "300 fresh prompts on 2026-11-14 through OpenRouter, each pinned to its maker's own "
            "standard tier, with the same prompts, token limits, retry policy, and grading as "
            "the Checkpoint 3 pool."
        ]
    second = "second router" if spec.pools == ("flagship",) else "study's router"
    whose = "flagships'" if single == "flagship" else "added models'"
    return PoolStudyReport(
        study_id=spec.study_id,
        title=spec.title,
        question=spec.question.format(added=len(added)),
        base_snapshot_id=base.snapshot_id,
        added_snapshot_ids=[listed[pool.name].snapshot_id for pool in pools],
        added=added,
        added_from={model.id: pool.name for pool in pools for model in complete[pool.name]},
        excluded=excluded,
        strongest_added_id=top,
        router=summary,
        protocol=[
            *intro,
            *(f"{item.display_name} is left out: {item.reason}" for item in excluded),
            f"The {second} uses the Checkpoint 3 recipe unchanged on all "
            f"{len(router.pool_ids)} models: "
            "classifier family and regularization chosen on validation log loss, presets tuned "
            "on the validation split with the same grids and accuracy floors, then refit on "
            "train + validation.",
            f"The strongest {single}, {names[top]}, is the one with the most right answers on "
            "the train and validation prompts, fixed before the test and fresh results were read.",
            f"The paired comparisons were fixed in code before the {whose} results were read; "
            "p-values are Holm-adjusted within each evaluation. Intervals are "
            "95% bootstrap intervals over prompts (10,000 resamples, fixed seed).",
            spec.reuse_note,
        ],
        evaluations=evaluations,
        suite_matrix=matrix_summary(
            suites["cp3"].cells, {model.id: model for model in pool_snapshot.models}
        ),
        cell_tables=[table.relative_to(REPOSITORY_ROOT).as_posix() for table in tables],
        spend_usd={
            suite: round(sum(float(meta["provider_billed_spend_usd"].get(suite, 0.0))
                             for meta in metas.values()), 6)
            for suite in ("cp3", "final")
        },
        spend_by_model_usd={model_id: by_model[model_id] for model_id in sorted(by_model)},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--study", choices=sorted(STUDIES), required=True)
    parser.add_argument("--from-runs", action="store_true",
                        help="Rebuild the added pools' cell tables from the raw local runs")
    args = parser.parse_args()
    spec = STUDIES[args.study]
    if args.from_runs:
        for pool in spec.added:
            meta = build_cells(ADDED_POOLS[pool.name])
            print(f"{pool.name} cells: {meta['rows_by_model']}, "
                  f"spend {meta['provider_billed_spend_usd']}")
    report = build_report(spec)
    spec.report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    router = report.router
    for name, classifier in router.classifiers.items():
        print(f"{name}: val log loss {classifier.validation.log_loss:.4f} "
              f"{classifier.best_params}")
    print(f"per-task reference: val log loss {router.reference_model_task_prior.log_loss:.4f}")
    for result in router.weight_tuning:
        print(f"tuned {result.priority.value}: {result.weights.model_dump()} -> "
              f"{result.validation_correct}/{router.validation_prompts}")
    print(f"strongest added: {report.strongest_added_id}; excluded: "
          f"{[item.model_id for item in report.excluded]}")
    for evaluation in report.evaluations:
        print(f"{evaluation.title}: {evaluation.prompts} prompts, "
              f"log loss {evaluation.classifier.log_loss:.4f} "
              f"(table {evaluation.reference_model_task_prior.log_loss:.4f})")
        summarize(evaluation.strategies + evaluation.oracle, evaluation.evaluation_id)
        for comparison in evaluation.comparisons:
            print(f"  {comparison.strategy_id} vs {comparison.baseline_id}: "
                  f"{comparison.accuracy_difference:+.3f} Holm p={comparison.holm_p:.3f}, "
                  f"cost ratio {comparison.cost_ratio}")
    print(f"wrote {spec.report_path.relative_to(REPOSITORY_ROOT)} and "
          f"{spec.router_path.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
