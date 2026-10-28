import random
from decimal import Decimal

import numpy as np
import pytest

from app.benchmarks.suite import Benchmark, RouterSplit, SuiteItem, TaskGroup
from app.learned.features import Cell, ModelHistory, feature_row, prompt_features
from app.learned.train import (
    build_dataset,
    fit_and_compare,
    matrix_summary,
    model_task_prior,
    replay_routing,
)
from app.registry.pool import Access, PoolModel

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


def test_routing_replay_compares_baselines_and_learned_policies() -> None:
    items, cells = _synthetic()
    history = ModelHistory(cells)
    train = build_dataset(RouterSplit.TRAIN, cells, items, MODELS, history)
    validation = build_dataset(RouterSplit.VALIDATION, cells, items, MODELS, history)
    report = fit_and_compare(train, validation)
    probabilities = {
        name: entry["_model"].predict_proba(validation.x)[:, 1] for name, entry in report.items()
    }
    probabilities["model_task_prior"] = model_task_prior(cells, validation, items)
    replay = replay_routing(validation, probabilities, cells, items, MODELS)
    strategies = replay["strategies"]
    assert replay["validation_prompts_with_all_models"] == 18
    assert strategies["fixed_strongest"]["accuracy"] == 1.0
    assert strategies["fixed_strongest"]["selected_models"] == {"gemini-4-argon": 18}
    assert all(
        sum(entry["selected_models"].values()) == entry["prompts"] for entry in strategies.values()
    )
    assert "model_task_prior:balanced" in strategies
    learned_cost = strategies["logistic_regression:cost"]
    # The learned router should keep most of the quality while spending less than always-strong.
    assert learned_cost["total_cost_usd"] < strategies["fixed_strongest"]["total_cost_usd"]
    assert learned_cost["accuracy"] >= strategies["fixed_cheapest"]["accuracy"]
    assert np.isfinite(strategies["gradient_boosted_trees:quality"]["accuracy"])


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
