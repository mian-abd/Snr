"""Train, select, tune, and evaluate the learned router (proposal weeks of Oct 22 to Nov 5).

    uv run --project backend python -m app.learned.train --run-id cp3-full

1. Fit logistic regression and gradient-boosted trees for P(success | prompt, model) on the
   training split and compare them on the validation split (log loss, Brier, AUC, overfitting).
2. Select the family with the lower validation log loss, the proposal's rule, and replay
   validation routing for every family with the starting weight presets.
3. Tune one weight preset per user priority on the validation split with the selected family.
4. Refit the selected family on the training and validation splits and export it to
   ``data/learned/cp3-router-model.json``, which the API serves without scikit-learn.
5. Evaluate that exported router once on the held-out test split against the fixed baselines,
   the Checkpoint 2 rule router, and a model-by-task reference. Nothing is tuned on test.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from app.benchmarks.suite import RouterSplit, SuiteItem, TaskGroup, load_suite
from app.config import REPOSITORY_ROOT
from app.domain.models import (
    ClassifierMetrics,
    ClassifierReport,
    HeldoutEvaluation,
    LearnedMatrixRow,
    LearnedRouterReport,
    LearnedStrategyOutcome,
    RoutingPriority,
    WeightTuningResult,
)
from app.learned.evaluate import (
    Chooser,
    complete_prompts,
    fixed_and_rule_choosers,
    oracle_chooser,
    replay,
    routing_errors,
    routing_estimates,
    score_chooser,
    tune_weights,
)
from app.learned.features import Cell, ModelHistory, feature_row
from app.learned.router import ROUTER_MODEL_PATH, LearnedRouter, RouterArtifact, policy_weights
from app.registry.pool import PoolModel, PoolSnapshot, load_pool
from app.routing.multi_objective import POLICY_WEIGHTS
from app.storage import read_jsonl

SUITE_PATH = REPOSITORY_ROOT / "data" / "benchmarks" / "cp3_suite.jsonl"
POOL_PATH = REPOSITORY_ROOT / "data" / "registry" / "cp3-pool-2026-10-27.json"
RUNS_DIR = REPOSITORY_ROOT / "data" / "local" / "cp3"
REPORT_DIR = REPOSITORY_ROOT / "data" / "learned"

TRAIN_ONLY = frozenset({RouterSplit.TRAIN})
FIT_SPLITS = frozenset({RouterSplit.TRAIN, RouterSplit.VALIDATION})
# Week of Nov 5: the Oct 29 grid's best C (0.01) sat on its edge, so the grid now extends below.
LR_GRID = [
    {"logisticregression__C": value} for value in (0.001, 0.003, 0.01, 0.03, 0.1, 1.0, 10.0)
]
GBT_GRID = [
    {"max_depth": depth, "learning_rate": rate, "max_iter": iterations}
    for depth in (2, 3)
    for rate in (0.05, 0.1)
    for iterations in (100, 300)
]
SELECTION_RULE = (
    "Lower validation log loss between logistic regression and gradient-boosted trees, as the "
    "proposal specifies; the train-to-validation gap is the overfitting check."
)
FAMILY_FACTORIES: dict[str, Callable[[], Any]] = {
    "logistic_regression": lambda: make_pipeline(
        StandardScaler(), LogisticRegression(max_iter=5000)
    ),
    "gradient_boosted_trees": lambda: HistGradientBoostingClassifier(
        l2_regularization=1.0, random_state=0
    ),
}
FAMILY_GRIDS: dict[str, list[dict[str, Any]]] = {
    "logistic_regression": LR_GRID,
    "gradient_boosted_trees": GBT_GRID,
}


def load_cells(run_dir: Path, items: dict[str, SuiteItem]) -> list[Cell]:
    """Collect scored cells. Unscored code answers (awaiting EvalPlus) are left out."""
    code_scores: dict[tuple[str, str], bool] = {}
    for path in run_dir.glob("*/code_scores.jsonl"):
        for row in read_jsonl(path):
            code_scores[(row["model_id"], row["sample_id"])] = bool(row["passed"])
    cells: list[Cell] = []
    for path in run_dir.glob("*/results.jsonl"):
        for row in read_jsonl(path):
            item = items.get(row["sample_id"])
            if item is None:
                continue
            correct = row["correct"]
            if correct is None:
                correct = code_scores.get((row["model_id"], row["sample_id"]))
            if correct is None:
                continue
            result = row["result"]
            cells.append(
                Cell(
                    sample_id=row["sample_id"],
                    model_id=row["model_id"],
                    task_group=item.task_group,
                    router_split=item.router_split,
                    correct=bool(correct),
                    served=result["status"] == "success",
                    latency_ms=float(result["latency_ms"]),
                    completion_tokens=result.get("completion_tokens"),
                    cost_usd=float(result.get("cost_usd") or 0.0),
                )
            )
    return cells


@dataclass
class Dataset:
    names: list[str]
    x: np.ndarray
    y: np.ndarray
    keys: list[tuple[str, str]]  # (sample_id, model_id)

    def probability(self, values: np.ndarray) -> Callable[[str, str], float]:
        index = {key: position for position, key in enumerate(self.keys)}
        return lambda sample_id, model_id: float(values[index[(sample_id, model_id)]])


def build_dataset(
    split: RouterSplit | frozenset[RouterSplit],
    cells: list[Cell],
    items: dict[str, SuiteItem],
    models: dict[str, PoolModel],
    history: ModelHistory,
) -> Dataset:
    splits = frozenset({split}) if isinstance(split, RouterSplit) else split
    pool_ids = sorted(models)
    rows: list[dict[str, float]] = []
    labels: list[int] = []
    keys: list[tuple[str, str]] = []
    for cell in cells:
        if cell.router_split not in splits or cell.model_id not in models:
            continue
        rows.append(feature_row(items[cell.sample_id], models[cell.model_id], history, pool_ids))
        labels.append(int(cell.correct))
        keys.append((cell.sample_id, cell.model_id))
    names = sorted(rows[0]) if rows else []
    x = np.array([[row[name] for name in names] for row in rows], dtype=float)
    return Dataset(names, x, np.array(labels, dtype=int), keys)


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float | None]:
    clipped = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "log_loss": float(log_loss(y, clipped, labels=[0, 1])),
        "brier": float(brier_score_loss(y, clipped)),
        "roc_auc": float(roc_auc_score(y, clipped)) if len(set(y.tolist())) == 2 else None,
        "accuracy_at_0_5": float(np.mean((clipped >= 0.5) == y)),
        "rows": int(len(y)),
    }


def fit_and_compare(train: Dataset, validation: Dataset) -> dict[str, Any]:
    """Pick each family's best setting by validation log loss and report the overfitting gap."""
    report: dict[str, Any] = {}
    for name, factory in FAMILY_FACTORIES.items():
        trials = []
        for params in FAMILY_GRIDS[name]:
            model: Pipeline | HistGradientBoostingClassifier = factory()
            model.set_params(**params)
            model.fit(train.x, train.y)
            trials.append(
                {
                    "params": params,
                    "train": _metrics(train.y, model.predict_proba(train.x)[:, 1]),
                    "validation": _metrics(validation.y, model.predict_proba(validation.x)[:, 1]),
                    "model": model,
                }
            )
        best = min(trials, key=lambda trial: trial["validation"]["log_loss"])
        report[name] = {
            "best_params": best["params"],
            "train": best["train"],
            "validation": best["validation"],
            "overfit_gap_log_loss": best["validation"]["log_loss"] - best["train"]["log_loss"],
            "grid": [
                {key: value for key, value in trial.items() if key != "model"} for trial in trials
            ],
            "_model": best["model"],
        }
    return report


def select_family(comparison: dict[str, Any]) -> str:
    return min(
        comparison,
        key=lambda name: (
            comparison[name]["validation"]["log_loss"],
            comparison[name]["overfit_gap_log_loss"],
        ),
    )


def model_task_prior(
    cells: list[Cell],
    dataset: Dataset,
    items: dict[str, SuiteItem],
    splits: frozenset[RouterSplit] = TRAIN_ONLY,
) -> np.ndarray:
    """Reference with no prompt features: each model's success rate on the task group."""
    history = ModelHistory(cells, splits)
    return np.array(
        [
            history.success_rate(model_id, items[sample_id].task_group, None)
            for sample_id, model_id in dataset.keys
        ],
        dtype=float,
    )


def matrix_summary(cells: list[Cell], models: dict[str, PoolModel]) -> list[LearnedMatrixRow]:
    """Per-model outcomes over every split, strongest first."""
    by_model: dict[str, list[Cell]] = defaultdict(list)
    for cell in cells:
        by_model[cell.model_id].append(cell)
    rows = []
    for model_id, members in by_model.items():
        served = [cell.latency_ms for cell in members if cell.served]
        rows.append(
            LearnedMatrixRow(
                model_id=model_id,
                display_name=models[model_id].display_name,
                access=models[model_id].access.value,
                prompts=len(members),
                correct=sum(cell.correct for cell in members),
                prompts_by_task={
                    group.value: sum(cell.task_group == group for cell in members)
                    for group in TaskGroup
                },
                correct_by_task={
                    group.value: sum(cell.task_group == group and cell.correct for cell in members)
                    for group in TaskGroup
                },
                failed_calls=sum(not cell.served for cell in members),
                median_latency_ms=round(median(served), 1) if served else None,
                cost_usd=round(sum(cell.cost_usd for cell in members), 6),
            )
        )
    return sorted(rows, key=lambda row: (-row.correct, row.model_id))


def validation_replay(
    validation: Dataset,
    probabilities: dict[str, np.ndarray],
    cells: list[Cell],
    items: dict[str, SuiteItem],
    models: dict[str, PoolModel],
    tuned: list[WeightTuningResult] | None = None,
    tuned_family: str | None = None,
) -> tuple[int, list[LearnedStrategyOutcome]]:
    """Fixed, rule, and every family under the starting presets; the tuned presets if given."""
    model_ids = sorted(models)
    prompts = complete_prompts(cells, RouterSplit.VALIDATION, model_ids)
    estimates = routing_estimates(cells, TRAIN_ONLY)
    choosers: dict[str, Chooser] = dict(fixed_and_rule_choosers(items, model_ids))
    for family, values in probabilities.items():
        for priority in RoutingPriority:
            choosers[f"{family}:{priority.value}"] = score_chooser(
                validation.probability(values), estimates, model_ids, items,
                POLICY_WEIGHTS[priority],
            )
    if tuned and tuned_family:
        for result in tuned:
            choosers[f"{tuned_family}_tuned:{result.priority.value}"] = score_chooser(
                validation.probability(probabilities[tuned_family]), estimates, model_ids,
                items, policy_weights(result.weights),
            )
    return len(prompts), replay(prompts, choosers, cells, items)


def export_router(
    family: str,
    params: dict[str, Any],
    fit: Dataset,
    history: ModelHistory,
    cells: list[Cell],
    tuned: list[WeightTuningResult],
    snapshot: PoolSnapshot,
    run_id: str,
    models: dict[str, PoolModel],
) -> tuple[RouterArtifact, Pipeline]:
    """Refit the selected family on ``fit`` and describe it as plain numbers."""
    if family != "logistic_regression":
        raise ValueError(f"Only the linear router can be exported, not {family}")
    model: Pipeline = FAMILY_FACTORIES[family]()
    model.set_params(**params)
    model.fit(fit.x, fit.y)
    scaler = model.named_steps["standardscaler"]
    linear = model.named_steps["logisticregression"]
    artifact = RouterArtifact(
        artifact_id=f"{run_id}-{family}-C{params['logisticregression__C']}",
        run_id=run_id,
        pool_snapshot_id=snapshot.snapshot_id,
        family=family,
        params=params,
        selection_rule=SELECTION_RULE,
        trained_on_splits=sorted(split.value for split in history.splits),
        training_rows=len(fit.y),
        model_ids=sorted(models),
        features=fit.names,
        scaler_mean=[float(value) for value in scaler.mean_],
        scaler_scale=[float(value) for value in scaler.scale_],
        coefficients=[float(value) for value in linear.coef_[0]],
        intercept=float(linear.intercept_[0]),
        history=history.snapshot(),
        estimates=routing_estimates(cells, history.splits),
        weights={result.priority: result.weights for result in tuned},
    )
    return artifact, model


def heldout_evaluation(
    router: LearnedRouter,
    fitted: Pipeline,
    cells: list[Cell],
    items: dict[str, SuiteItem],
    models: dict[str, PoolModel],
) -> HeldoutEvaluation:
    """The exported router on the test split, read once, against every baseline."""
    history = ModelHistory(cells, FIT_SPLITS)
    test = build_dataset(RouterSplit.TEST, cells, items, models, history)
    sklearn_p = fitted.predict_proba(test.x)[:, 1]
    served_p = np.array(
        [
            router.p_success(
                items[sample].question, items[sample].task_group, len(items[sample].options),
                router.models[model_id],
            )
            for sample, model_id in test.keys
        ]
    )
    if not np.allclose(sklearn_p, served_p, atol=1e-9):
        raise RuntimeError("The exported router does not reproduce the fitted model")
    prior = model_task_prior(cells, test, items, FIT_SPLITS)
    model_ids = sorted(models)
    prompts = complete_prompts(cells, RouterSplit.TEST, model_ids)
    estimates = router.artifact.estimates
    choosers: dict[str, Chooser] = dict(fixed_and_rule_choosers(items, model_ids))
    for priority in RoutingPriority:
        weights = router.artifact.weights[priority]

        def learned(sample: str, weights: Any = weights) -> str:
            item = items[sample]
            return router.decide_for(
                item.question, group=item.task_group, option_count=len(item.options),
                weights=weights,
            )[0]

        choosers[f"learned:{priority.value}"] = learned
    for priority in RoutingPriority:
        choosers[f"model_task_prior:{priority.value}"] = score_chooser(
            test.probability(prior), estimates, model_ids, items,
            policy_weights(router.artifact.weights[priority]),
        )
    # Week of Nov 12: the oracle with perfect hindsight, and where the router under- or
    # over-routes, both for the same priorities and weights.
    test_cells = [cell for cell in cells if cell.router_split == RouterSplit.TEST]
    oracles: dict[str, Chooser] = {
        f"oracle:{priority.value}": oracle_chooser(
            test_cells, model_ids, policy_weights(router.artifact.weights[priority])
        )
        for priority in RoutingPriority
    }
    return HeldoutEvaluation(
        artifact_id=router.artifact.artifact_id,
        trained_on=router.artifact.trained_on_splits,
        prompts=len(prompts),
        classifier=ClassifierMetrics.model_validate(_metrics(test.y, sklearn_p)),
        reference_model_task_prior=ClassifierMetrics.model_validate(_metrics(test.y, prior)),
        strategies=replay(prompts, choosers, cells, items),
        oracle=replay(prompts, oracles, cells, items),
        routing_errors=[
            routing_errors(f"learned:{priority.value}", prompts,
                           choosers[f"learned:{priority.value}"], test_cells, estimates, items)
            for priority in RoutingPriority
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", default="cp3-full")
    args = parser.parse_args()
    snapshot: PoolSnapshot = load_pool(POOL_PATH)
    items = {item.sample_id: item for item in load_suite(SUITE_PATH)}
    cells = load_cells(RUNS_DIR / args.run_id, items)
    present = {cell.model_id for cell in cells}
    models = {model.id: model for model in snapshot.models if model.id in present}
    history = ModelHistory(cells)
    train = build_dataset(RouterSplit.TRAIN, cells, items, models, history)
    validation = build_dataset(RouterSplit.VALIDATION, cells, items, models, history)
    if not len(train.y) or not len(validation.y):
        print("Not enough scored cells yet to train.")
        return 1

    comparison = fit_and_compare(train, validation)
    selected = select_family(comparison)
    probabilities = {
        name: entry["_model"].predict_proba(validation.x)[:, 1]
        for name, entry in comparison.items()
    }
    # Routing on the prior too shows what the prompt features add beyond a model-by-task table.
    probabilities["model_task_prior"] = model_task_prior(cells, validation, items)
    validation_prompts = complete_prompts(cells, RouterSplit.VALIDATION, sorted(models))
    tuned = tune_weights(
        validation_prompts, validation.probability(probabilities[selected]),
        routing_estimates(cells, TRAIN_ONLY), sorted(models), cells, items,
    )
    prompt_count, strategies = validation_replay(
        validation, probabilities, cells, items, models, tuned, selected
    )

    fit_history = ModelHistory(cells, FIT_SPLITS)
    fit = build_dataset(FIT_SPLITS, cells, items, models, fit_history)
    artifact, fitted = export_router(
        selected, comparison[selected]["best_params"], fit, fit_history, cells, tuned,
        snapshot, args.run_id, models,
    )
    ROUTER_MODEL_PATH.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
    router = LearnedRouter(artifact, snapshot)
    heldout = heldout_evaluation(router, fitted, cells, items, models)

    report = LearnedRouterReport(
        run_id=args.run_id,
        pool_snapshot_id=snapshot.snapshot_id,
        models=sorted(models),
        models_without_results=sorted(m.id for m in snapshot.models if m.id not in models),
        features=train.names,
        rows={"train": len(train.y), "validation": len(validation.y)},
        matrix=matrix_summary(cells, models),
        classifiers={
            name: ClassifierReport.model_validate(
                {key: value for key, value in entry.items() if key != "_model"}
            )
            for name, entry in comparison.items()
        },
        reference_model_task_prior=ClassifierMetrics.model_validate(
            _metrics(validation.y, probabilities["model_task_prior"])
        ),
        selected_family=selected,
        selection_rule=SELECTION_RULE,
        validation_prompts=prompt_count,
        strategies=strategies,
        weight_tuning=tuned,
        heldout=heldout,
        note=(
            "Classifiers were selected and weights tuned on the validation split. The selected "
            "router was then refit on training and validation data and evaluated once on the "
            "held-out test split."
        ),
    )
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{args.run_id}-router-comparison.json"
    out.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    for name, classifier in report.classifiers.items():
        print(f"{name}: val log loss {classifier.validation.log_loss:.4f}, "
              f"AUC {classifier.validation.roc_auc}, gap {classifier.overfit_gap_log_loss:.4f}")
    prior = report.reference_model_task_prior
    print(f"model_task_prior: val log loss {prior.log_loss:.4f}, AUC {prior.roc_auc}")
    print(f"selected: {selected} {comparison[selected]['best_params']}")
    for result in tuned:
        print(f"tuned {result.priority.value}: {result.weights.model_dump()} -> "
              f"{result.validation_correct}/{prompt_count} correct, "
              f"${result.validation_cost_usd:.4f}")
    print(f"held-out test log loss {heldout.classifier.log_loss:.4f} "
          f"(reference {heldout.reference_model_task_prior.log_loss:.4f})")
    for strategy in heldout.strategies + heldout.oracle:
        print(f"  test {strategy.strategy_id}: {strategy.correct}/{strategy.prompts}, "
              f"${strategy.total_cost_usd:.4f}, median {strategy.median_latency_ms} ms")
    for errors in heldout.routing_errors:
        print(f"  errors {errors.strategy_id}: wrong {errors.wrong}, "
              f"under-routed {errors.under_routed}, over-routed {errors.over_routed}")
    print(f"wrote {out.relative_to(REPOSITORY_ROOT)} and "
          f"{ROUTER_MODEL_PATH.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
