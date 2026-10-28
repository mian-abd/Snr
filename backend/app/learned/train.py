"""Train and compare the lightweight routers (proposal weeks of Oct 22 and Oct 29).

    uv run --project backend python -m app.learned.train --run-id cp3-full

Fits logistic regression and gradient-boosted trees to predict P(success | prompt, model) on the
training split, compares them on the validation split, and replays routing decisions on the
validation prompts with the multi-objective scorer. The held-out test split is never read here.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
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
from app.domain.models import RoutingPriority
from app.learned.features import Cell, ModelHistory, feature_row
from app.registry.pool import PoolModel, PoolSnapshot, load_pool
from app.routing.multi_objective import CandidateEstimate, choose
from app.routing.policy import effort_score, prompt_signals
from app.storage import read_jsonl

SUITE_PATH = REPOSITORY_ROOT / "data" / "benchmarks" / "cp3_suite.jsonl"
POOL_PATH = REPOSITORY_ROOT / "data" / "registry" / "cp3-pool-2026-10-27.json"
RUNS_DIR = REPOSITORY_ROOT / "data" / "local" / "cp3"
REPORT_DIR = REPOSITORY_ROOT / "data" / "learned"

LR_GRID = [{"logisticregression__C": value} for value in (0.01, 0.1, 1.0, 10.0)]
GBT_GRID = [
    {"max_depth": depth, "learning_rate": rate, "max_iter": iterations}
    for depth in (2, 3)
    for rate in (0.05, 0.1)
    for iterations in (100, 300)
]
# Rule-router roles for this pool, mirroring the Checkpoint 2 paid policy.
CHEAPEST, FASTEST, STRONGEST = "gemma-4-26b", "mercury-3", "gemini-4-argon"


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


def build_dataset(
    split: RouterSplit,
    cells: list[Cell],
    items: dict[str, SuiteItem],
    models: dict[str, PoolModel],
    history: ModelHistory,
) -> Dataset:
    pool_ids = sorted(models)
    rows: list[dict[str, float]] = []
    labels: list[int] = []
    keys: list[tuple[str, str]] = []
    for cell in cells:
        if cell.router_split != split or cell.model_id not in models:
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
    families: dict[str, tuple[Any, list[dict[str, Any]]]] = {
        "logistic_regression": (
            lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000)),
            LR_GRID,
        ),
        "gradient_boosted_trees": (
            lambda: HistGradientBoostingClassifier(l2_regularization=1.0, random_state=0),
            GBT_GRID,
        ),
    }
    report: dict[str, Any] = {}
    for name, (factory, grid) in families.items():
        trials = []
        for params in grid:
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


def model_task_prior(
    cells: list[Cell], validation: Dataset, items: dict[str, SuiteItem]
) -> np.ndarray:
    """Reference with no prompt features: each model's training success rate on the task group."""
    counts: dict[tuple[str, TaskGroup], list[int]] = defaultdict(lambda: [0, 0])
    for cell in cells:
        if cell.router_split == RouterSplit.TRAIN:
            tally = counts[(cell.model_id, cell.task_group)]
            tally[0] += int(cell.correct)
            tally[1] += 1
    rates = []
    for sample_id, model_id in validation.keys:
        successes, total = counts[(model_id, items[sample_id].task_group)]
        rates.append((successes + 1) / (total + 2))
    return np.array(rates, dtype=float)


def _summarize(outcomes: list[tuple[bool, float, float]]) -> dict[str, float | int | None]:
    correct = sum(1 for ok, _, _ in outcomes if ok)
    cost = sum(cost for _, cost, _ in outcomes)
    latencies = sorted(latency for _, _, latency in outcomes)
    return {
        "prompts": len(outcomes),
        "correct": correct,
        "accuracy": correct / len(outcomes) if outcomes else 0.0,
        "total_cost_usd": round(cost, 6),
        "cost_per_correct_usd": round(cost / correct, 8) if correct else None,
        "median_latency_ms": round(median(latencies), 1) if latencies else None,
        "p95_latency_ms": (
            round(latencies[math.ceil(0.95 * len(latencies)) - 1], 1) if latencies else None
        ),
    }


def replay_routing(
    validation: Dataset,
    probabilities: dict[str, np.ndarray],
    cells: list[Cell],
    items: dict[str, SuiteItem],
    models: dict[str, PoolModel],
) -> dict[str, Any]:
    """Route each validation prompt once per strategy and look up that model's saved outcome."""
    by_key = {(cell.sample_id, cell.model_id): cell for cell in cells}
    train_cells = [cell for cell in cells if cell.router_split == RouterSplit.TRAIN]
    expected_cost: dict[tuple[str, TaskGroup], float] = {}
    expected_latency: dict[tuple[str, TaskGroup], float] = {}
    grouped: dict[tuple[str, TaskGroup], list[Cell]] = defaultdict(list)
    for cell in train_cells:
        grouped[(cell.model_id, cell.task_group)].append(cell)
    for key, members in grouped.items():
        expected_cost[key] = sum(cell.cost_usd for cell in members) / len(members)
        served = [cell.latency_ms for cell in members if cell.served] or [60000.0]
        expected_latency[key] = median(served)
    failure = {
        key: sum(1 for cell in members if not cell.served) / len(members)
        for key, members in grouped.items()
    }

    prompts = sorted({sample_id for sample_id, _ in validation.keys})
    complete = [
        sample_id for sample_id in prompts
        if all((sample_id, model_id) in by_key for model_id in models)
    ]

    def outcome(sample_id: str, model_id: str) -> tuple[bool, float, float]:
        cell = by_key[(sample_id, model_id)]
        return cell.correct, cell.cost_usd, cell.latency_ms

    strategies: dict[str, list[tuple[bool, float, float]]] = defaultdict(list)
    picks: dict[str, Counter[str]] = defaultdict(Counter)

    def route(strategy: str, sample_id: str, model_id: str) -> None:
        strategies[strategy].append(outcome(sample_id, model_id))
        picks[strategy][model_id] += 1

    index = {key: position for position, key in enumerate(validation.keys)}
    baselines = {CHEAPEST, FASTEST, STRONGEST} <= set(models)
    for sample_id in complete:
        item = items[sample_id]
        group = item.task_group
        if baselines:
            route("fixed_cheapest", sample_id, CHEAPEST)
            route("fixed_strongest", sample_id, STRONGEST)
            score = effort_score(prompt_signals(item.question))
            route("rule_balanced", sample_id,
                  STRONGEST if score >= 3 else FASTEST if score else CHEAPEST)
        for family, probs in probabilities.items():
            for priority in RoutingPriority:
                candidates = [
                    CandidateEstimate(
                        model_id=model_id,
                        p_success=float(probs[index[(sample_id, model_id)]]),
                        expected_cost_usd=expected_cost.get((model_id, group), 0.0),
                        expected_latency_ms=expected_latency.get((model_id, group), 60000.0),
                        failure_rate=failure.get((model_id, group), 0.0),
                    )
                    for model_id in sorted(models)
                ]
                route(f"{family}:{priority.value}", sample_id,
                      choose(candidates, priority).model_id)
    return {
        "validation_prompts_with_all_models": len(complete),
        "strategies": {
            name: {**_summarize(rows), "selected_models": dict(picks[name].most_common())}
            for name, rows in strategies.items()
        },
    }


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
    probabilities = {
        name: entry["_model"].predict_proba(validation.x)[:, 1]
        for name, entry in comparison.items()
    }
    # Routing on the prior too shows what the prompt features add beyond a model-by-task table.
    probabilities["model_task_prior"] = model_task_prior(cells, validation, items)
    routing = replay_routing(validation, probabilities, cells, items, models)
    report = {
        "run_id": args.run_id,
        "pool_snapshot_id": snapshot.snapshot_id,
        "models": sorted(models),
        "features": train.names,
        "rows": {"train": len(train.y), "validation": len(validation.y)},
        "classifiers": {
            name: {key: value for key, value in entry.items() if key != "_model"}
            for name, entry in comparison.items()
        },
        "reference_model_task_prior": {
            "validation": _metrics(validation.y, probabilities["model_task_prior"])
        },
        "routing_on_validation": routing,
        "note": "Validation split only; the held-out test split is reserved for Checkpoint 3.",
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{args.run_id}-router-comparison.json"
    out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    for name, entry in report["classifiers"].items():
        print(f"{name}: val log loss {entry['validation']['log_loss']:.4f}, "
              f"AUC {entry['validation']['roc_auc']}, gap {entry['overfit_gap_log_loss']:.4f}")
    prior = report["reference_model_task_prior"]["validation"]
    print(f"model_task_prior: val log loss {prior['log_loss']:.4f}, AUC {prior['roc_auc']}")
    print(f"wrote {out.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
