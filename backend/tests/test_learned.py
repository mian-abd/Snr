import json
import random
from decimal import Decimal

import numpy as np
import pytest

from app.benchmarks.suite import Benchmark, RouterSplit, SuiteItem, TaskGroup
from app.domain.models import (
    LearnedRouteRequest,
    LearnedStrategyOutcome,
    RoutingPriority,
    StrategyTaskOutcome,
)
from app.learned.evaluate import complete_prompts, routing_estimates, tune_weights, weight_grid
from app.learned.features import (
    Cell,
    ModelHistory,
    count_options,
    feature_row,
    infer_task_group,
    prompt_features,
)
from app.learned.plots import _points
from app.learned.router import LearnedRouter, NoEligibleModelError, RouterArtifact
from app.learned.train import (
    FIT_SPLITS,
    TRAIN_ONLY,
    build_dataset,
    export_router,
    fit_and_compare,
    matrix_summary,
    model_task_prior,
    select_family,
    validation_replay,
)
from app.registry.pool import Access, PoolModel, PoolSnapshot, models_sha256

GROUPS = {Benchmark.GSM8K: TaskGroup.MATH, Benchmark.MMLU_PRO: TaskGroup.QA}


def _model(model_id: str, price_out: str, access: Access = Access.PAID) -> PoolModel:
    return PoolModel(
        id=model_id, display_name=model_id, family="f", open_weight=True, parameters="?",
        access=access, provider="test", base_url="http://x", upstream_model=model_id,
        prompt_price_per_token=Decimal(price_out) / 4 if access == Access.PAID else Decimal(0),
        completion_price_per_token=Decimal(price_out) if access == Access.PAID else Decimal(0),
        context_length=1000, requests_per_minute=60, data_policy="test",
    )


MODELS = {
    "gemma-4-26b": _model("gemma-4-26b", "0.0000003"),
    "mercury-3": _model("mercury-3", "0.00000035"),
    "gemini-4-argon": _model("gemini-4-argon", "0.00001"),
}


def _item(index: int, split: RouterSplit, benchmark: Benchmark = Benchmark.GSM8K) -> SuiteItem:
    hard = index % 3 == 0
    question = ("Calculate 12 + 7 + 5 + 9 then explain. " * (6 if hard else 1)).strip()
    return SuiteItem(
        sample_id=f"{benchmark.value}-{index:03d}", benchmark=benchmark,
        task_group=GROUPS[benchmark], dataset="d", source_split="test", revision="r",
        source_id=str(index), question=question,
        options=["a", "b", "c", "d"] if benchmark == Benchmark.MMLU_PRO else [],
        expected_answer="1", router_split=split,
    )


def _synthetic(seed: int = 0) -> tuple[dict[str, SuiteItem], list[Cell]]:
    """Strong model solves everything; cheap models fail the long ("hard") prompts."""
    rng = random.Random(seed)
    items: dict[str, SuiteItem] = {}
    cells: list[Cell] = []
    splits = [RouterSplit.TRAIN] * 6 + [RouterSplit.VALIDATION] * 2 + [RouterSplit.TEST] * 2
    for index in range(90):
        benchmark = Benchmark.GSM8K if index % 2 else Benchmark.MMLU_PRO
        item = _item(index, splits[index % 10], benchmark)
        items[item.sample_id] = item
        hard = index % 3 == 0
        for model_id, cost, latency in (
            ("gemma-4-26b", 0.0001, 3000.0),
            ("mercury-3", 0.0001, 600.0),
            ("gemini-4-argon", 0.003, 5000.0),
        ):
            strong = model_id == "gemini-4-argon"
            correct = strong or (not hard and rng.random() > 0.1)
            cells.append(Cell(item.sample_id, model_id, item.task_group, item.router_split,
                              correct, True, latency, 200, cost))
    return items, cells


def test_prompt_features_capture_task_length_and_signals() -> None:
    long_item = _item(0, RouterSplit.TRAIN)
    short_item = _item(1, RouterSplit.TRAIN)
    long_features, short_features = prompt_features(long_item), prompt_features(short_item)
    assert long_features["task_math"] == 1.0 and long_features["task_qa"] == 0.0
    assert long_features["log_words"] > short_features["log_words"]
    assert long_features["signal_long"] == 1.0 and short_features["signal_long"] == 0.0
    assert long_features["effort_score"] >= short_features["effort_score"]
    mcq = prompt_features(_item(2, RouterSplit.TRAIN, Benchmark.MMLU_PRO))
    assert mcq["option_count"] == 4.0 and mcq["task_qa"] == 1.0


def test_history_uses_training_rows_only_and_leaves_the_own_prompt_out() -> None:
    train_hit = Cell("a", "m", TaskGroup.MATH, RouterSplit.TRAIN, True, True, 100.0, 10, 0.0)
    train_miss = Cell("b", "m", TaskGroup.MATH, RouterSplit.TRAIN, False, True, 300.0, 30, 0.0)
    leaked = Cell("c", "m", TaskGroup.MATH, RouterSplit.TEST, True, True, 9999.0, 999, 0.0)
    history = ModelHistory([train_hit, train_miss, leaked])
    # (1 hit + 1 prior) / (2 rows + 2 prior); the test row never counts.
    assert history.success_rate("m", TaskGroup.MATH, exclude_sample=None) == pytest.approx(0.5)
    # Excluding prompt "a" removes its own label: (0 + 1) / (1 + 2).
    assert history.success_rate("m", TaskGroup.MATH, exclude_sample="a") == pytest.approx(1 / 3)
    assert history.latency_ms["m"] == pytest.approx(200.0)


def test_feature_rows_are_aligned_and_training_rows_exclude_their_label() -> None:
    items, cells = _synthetic()
    history = ModelHistory(cells)
    ids = sorted(MODELS)
    train_item = next(item for item in items.values() if item.router_split == RouterSplit.TRAIN)
    row = feature_row(train_item, MODELS["gemma-4-26b"], history, ids)
    assert row["model_gemma-4-26b"] == 1.0 and row["model_gemini-4-argon"] == 0.0
    expected = history.success_rate("gemma-4-26b", train_item.task_group, train_item.sample_id)
    assert row["historical_success"] == pytest.approx(expected)
    other = feature_row(train_item, MODELS["gemini-4-argon"], history, ids)
    assert sorted(row) == sorted(other)


def test_both_classifiers_train_and_report_validation_metrics() -> None:
    items, cells = _synthetic()
    history = ModelHistory(cells)
    train = build_dataset(RouterSplit.TRAIN, cells, items, MODELS, history)
    validation = build_dataset(RouterSplit.VALIDATION, cells, items, MODELS, history)
    assert len(train.y) == 54 * 3 // 1 and len(validation.y) == 18 * 3
    assert not {sample for sample, _ in validation.keys} & {sample for sample, _ in train.keys}
    report = fit_and_compare(train, validation)
    for name in ("logistic_regression", "gradient_boosted_trees"):
        entry = report[name]
        assert entry["validation"]["roc_auc"] > 0.8
        assert entry["validation"]["log_loss"] == min(
            trial["validation"]["log_loss"] for trial in entry["grid"]
        )
        assert "overfit_gap_log_loss" in entry


def _trained(items: dict[str, SuiteItem], cells: list[Cell]):
    history = ModelHistory(cells)
    train = build_dataset(RouterSplit.TRAIN, cells, items, MODELS, history)
    validation = build_dataset(RouterSplit.VALIDATION, cells, items, MODELS, history)
    report = fit_and_compare(train, validation)
    probabilities = {
        name: entry["_model"].predict_proba(validation.x)[:, 1] for name, entry in report.items()
    }
    probabilities["model_task_prior"] = model_task_prior(cells, validation, items)
    return report, validation, probabilities


def _tuned(items, cells, validation, probabilities):
    prompts = complete_prompts(cells, RouterSplit.VALIDATION, sorted(MODELS))
    return tune_weights(
        prompts, validation.probability(probabilities["logistic_regression"]),
        routing_estimates(cells, TRAIN_ONLY), sorted(MODELS), cells, items,
    )


def test_routing_replay_compares_baselines_and_learned_policies() -> None:
    items, cells = _synthetic()
    _, validation, probabilities = _trained(items, cells)
    tuned = _tuned(items, cells, validation, probabilities)
    count, outcomes = validation_replay(
        validation, probabilities, cells, items, MODELS, tuned, "logistic_regression"
    )
    strategies = {outcome.strategy_id: outcome for outcome in outcomes}
    assert count == 18
    assert strategies["fixed_strongest"].accuracy == 1.0
    assert strategies["fixed_strongest"].selected_models == {"gemini-4-argon": 18}
    assert all(sum(entry.selected_models.values()) == entry.prompts for entry in outcomes)
    assert all(
        sum(task.prompts for task in entry.by_task.values()) == entry.prompts for entry in outcomes
    )
    assert "model_task_prior:balanced" in strategies
    assert "logistic_regression_tuned:quality" in strategies
    learned_cost = strategies["logistic_regression:cost"]
    # The learned router should keep most of the quality while spending less than always-strong.
    assert learned_cost.total_cost_usd < strategies["fixed_strongest"].total_cost_usd
    assert learned_cost.accuracy >= strategies["fixed_cheapest"].accuracy
    assert np.isfinite(strategies["gradient_boosted_trees:quality"].accuracy)


def test_tuned_presets_respect_their_accuracy_floors() -> None:
    items, cells = _synthetic()
    report, validation, probabilities = _trained(items, cells)
    assert select_family(report) in report
    tuned = {result.priority: result for result in _tuned(items, cells, validation, probabilities)}
    assert set(tuned) == set(RoutingPriority)
    quality = tuned[RoutingPriority.QUALITY]
    assert quality.accuracy_floor is None
    assert quality.candidates_tried == len(weight_grid(RoutingPriority.QUALITY))
    for priority in (RoutingPriority.COST, RoutingPriority.LATENCY, RoutingPriority.BALANCED):
        result = tuned[priority]
        assert result.accuracy_floor is not None
        assert result.validation_correct >= result.accuracy_floor
        assert result.validation_correct <= quality.validation_correct
    assert tuned[RoutingPriority.COST].validation_cost_usd <= quality.validation_cost_usd


def test_exported_router_reproduces_the_fitted_model_and_applies_hard_filters() -> None:
    items, cells = _synthetic()
    report, validation, probabilities = _trained(items, cells)
    tuned = _tuned(items, cells, validation, probabilities)
    fit_history = ModelHistory(cells, FIT_SPLITS)
    fit = build_dataset(FIT_SPLITS, cells, items, MODELS, fit_history)
    pool_models = list(MODELS.values())
    snapshot = PoolSnapshot(
        snapshot_id="test-pool", metadata_as_of="2026-11-03",
        models_sha256=models_sha256(pool_models), models=pool_models,
    )
    artifact, fitted = export_router(
        "logistic_regression", report["logistic_regression"]["best_params"], fit, fit_history,
        cells, tuned, snapshot, "test-run", MODELS,
    )
    router = LearnedRouter(RouterArtifact.model_validate_json(artifact.model_dump_json()), snapshot)
    test = build_dataset(RouterSplit.TEST, cells, items, MODELS, fit_history)
    served = [
        router.p_success(items[s].question, items[s].task_group, len(items[s].options),
                         MODELS[m])
        for s, m in test.keys
    ]
    assert np.allclose(served, fitted.predict_proba(test.x)[:, 1], atol=1e-9)

    hard = "Calculate 12 + 7 + 5 + 9 then explain. " * 6
    quality = router.decide(LearnedRouteRequest(prompt=hard, priority="quality"), set())
    assert quality.selected_model_id == "gemini-4-argon"
    assert quality.task_group == TaskGroup.MATH and quality.task_group_inferred
    assert quality.weights == router.artifact.weights[RoutingPriority.QUALITY]
    assert all(item.eligible and item.score is not None for item in quality.candidates)
    custom = router.decide(
        LearnedRouteRequest(prompt=hard, weights={"cost": 0, "latency": 10}), set()
    )
    assert custom.custom_weights and custom.selected_model_id == "mercury-3"  # fastest
    with pytest.raises(NoEligibleModelError):
        router.decide(LearnedRouteRequest(prompt=hard, min_context_tokens=5000), set())


def test_live_prompts_get_a_task_group_and_option_count() -> None:
    assert infer_task_group("def add(a, b):\n    return a + b") == TaskGroup.CODE
    assert infer_task_group("Calculate 15 percent of 240.") == TaskGroup.MATH
    question = "Which planet is largest?\nA. Mars\nB. Jupiter\nC. Venus\nD. Earth"
    assert count_options(question) == 4
    assert infer_task_group(question) == TaskGroup.QA
    assert infer_task_group("Explain the water cycle.") == TaskGroup.QA


def test_history_snapshot_round_trips_the_aggregates() -> None:
    _, cells = _synthetic()
    history = ModelHistory(cells, FIT_SPLITS)
    restored = ModelHistory.from_snapshot(json.loads(json.dumps(history.snapshot())))
    assert restored.splits == FIT_SPLITS
    for model_id in MODELS:
        for group in (TaskGroup.MATH, TaskGroup.QA):
            assert restored.success_rate(model_id, group, None) == pytest.approx(
                history.success_rate(model_id, group, None)
            )
        assert restored.latency_ms[model_id] == pytest.approx(history.latency_ms[model_id])
    assert restored.output_tokens == history.output_tokens


def test_matrix_summary_counts_every_split_per_model_and_task() -> None:
    items, cells = _synthetic()
    rows = matrix_summary(cells, MODELS)
    assert rows[0].model_id == "gemini-4-argon"  # solves everything, so it sorts first
    for row in rows:
        assert row.prompts == 90
        assert sum(row.prompts_by_task.values()) == row.prompts
        assert sum(row.correct_by_task.values()) == row.correct
        assert row.failed_calls == 0
    assert rows[0].correct == 90 and rows[0].prompts_by_task == {"math": 45, "qa": 45, "code": 0}


def test_plot_points_merge_strategies_that_land_on_the_same_spot() -> None:
    task = StrategyTaskOutcome(prompts=2, correct=2, accuracy=1.0, total_cost_usd=0.01,
                               median_latency_ms=1000.0)

    def outcome(strategy_id: str, correct: int, cost: float) -> LearnedStrategyOutcome:
        return LearnedStrategyOutcome(
            strategy_id=strategy_id, prompts=4, correct=correct, accuracy=correct / 4,
            total_cost_usd=cost, cost_per_correct_usd=None, median_latency_ms=1000.0,
            p95_latency_ms=None, selected_models={}, by_task={"math": task},
        )

    points = _points(
        [outcome("fixed_cheapest", 3, 0.01), outcome("learned:quality", 3, 0.01),
         outcome("learned:cost", 2, 0.0), outcome("model_task_prior:cost", 2, 0.0)],
        None,
    )
    labels = sorted(point.label for point in points if point.label)
    assert labels == ["Always cheapest = Learned · quality", "Learned · cost"]
    # A shared spot keeps one marker per series; the reference strategy is not plotted.
    assert len(points) == 3
    assert len(_points([outcome("learned:latency", 3, 0.0)], "math")) == 1
