import json
import random

import numpy as np
import pytest

from app.benchmarks import prepare_final
from app.benchmarks.suite import Benchmark, RouterSplit, SuiteItem, TaskGroup, load_suite
from app.config import REPOSITORY_ROOT
from app.domain.models import LiveCatalogStatus, ScenarioSpec
from app.learned import errors, stats
from app.learned.features import Cell
from app.learned.robustness import (
    Knowledge,
    RouterView,
    World,
    _unit_hash,
    catalog_knowledge,
    retired_call_latency,
)
from app.learned.router import ROUTER_MODEL_PATH, load_router
from app.registry.pool import load_pool

POOL = load_pool(REPOSITORY_ROOT / "data" / "registry" / "cp3-pool-2026-10-27.json")
SUITE = load_suite(REPOSITORY_ROOT / "data" / "benchmarks" / "cp3_suite.jsonl")
FINAL = load_suite(REPOSITORY_ROOT / "data" / "benchmarks" / "final_heldout.jsonl")
CATALOG = LiveCatalogStatus.model_validate_json(
    (REPOSITORY_ROOT / "data" / "registry" / "live-catalog-2026-11-13.json").read_text(
        encoding="utf-8"
    )
)


def test_final_set_is_fresh_balanced_and_matches_its_checksum() -> None:
    assert len(FINAL) == 300
    assert {item.router_split for item in FINAL} == {RouterSplit.FINAL}
    counts = {
        benchmark: sum(item.benchmark == benchmark for item in FINAL) for benchmark in Benchmark
    }
    assert counts == {Benchmark.GSM8K: 100, Benchmark.MMLU_PRO: 100,
                      Benchmark.HUMANEVAL_PLUS: 50, Benchmark.MBPP_PLUS: 50}
    used = {(item.benchmark, item.source_id) for item in SUITE}
    assert not used & {(item.benchmark, item.source_id) for item in FINAL}
    checkpoint1 = {"30", "263", "507", "509", "539", "756", "780", "851", "987", "1218",
                   "1227", "1251"}
    assert not checkpoint1 & {item.source_id for item in FINAL if item.benchmark == "gsm8k"}
    meta = json.loads(prepare_final.OUTPUT.with_suffix(".meta.json").read_text(encoding="utf-8"))
    import hashlib

    assert meta["final_sha256"] == hashlib.sha256(prepare_final.OUTPUT.read_bytes()).hexdigest()
    assert meta["seed"] == prepare_final.FINAL_SEED


def test_final_draw_excludes_used_prompts_deterministically() -> None:
    rows = [{"task_id": f"Mbpp/{n}", "prompt": f"def f{n}():", "entry_point": f"f{n}"}
            for n in range(120)]
    used = {f"Mbpp/{n}" for n in range(0, 120, 2)}
    first = prepare_final._evalplus(Benchmark.MBPP_PLUS, rows, used, random.Random(1))
    second = prepare_final._evalplus(Benchmark.MBPP_PLUS, rows, used, random.Random(1))
    assert first == second and len(first) == prepare_final.FINAL_SIZES[Benchmark.MBPP_PLUS]
    assert not used & {row["source_id"] for row in first}


def test_mcnemar_and_holm() -> None:
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(5, 5) == 1.0
    # 10 discordant prompts all favouring one side: 2 * 0.5**10.
    assert stats.mcnemar_exact(10, 0) == pytest.approx(2 / 1024)
    assert stats.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_paired_comparison_and_intervals_are_reproducible() -> None:
    a = stats.Outcomes.from_rows([(True, 0.01, 100.0)] * 8 + [(False, 0.01, 100.0)] * 2)
    b = stats.Outcomes.from_rows([(True, 0.02, 200.0)] * 6 + [(False, 0.02, 200.0)] * 4)
    indices = stats.bootstrap_indices(10)
    assert np.array_equal(indices, stats.bootstrap_indices(10))
    result = stats.compare("a", "b", "q", a, b, indices)
    assert (result.correct, result.baseline_correct) == (8, 6)
    assert (result.only_strategy_correct, result.only_baseline_correct) == (2, 0)
    assert result.cost_ratio == pytest.approx(0.5)
    assert result.median_latency_difference_ms == -100.0
    assert result.accuracy_difference_ci.low <= 0.2 <= result.accuracy_difference_ci.high
    spread = stats.uncertainty("a", a, indices)
    assert 0 <= spread.accuracy.low <= 0.8 <= spread.accuracy.high <= 1


def test_fast_replay_matches_the_live_router_with_and_without_the_catalog() -> None:
    router = load_router(ROUTER_MODEL_PATH, POOL)
    items = {item.sample_id: item for item in FINAL}
    prompts = sorted(items)[::7]
    view = RouterView(router, items, prompts)
    knowledge = catalog_knowledge(CATALOG)
    assert knowledge.unavailable == {"mercury-3"}
    assert knowledge.price == {"gemma-4-26b": pytest.approx(0.0675 / 0.0765)}
    for priority, weights in router.artifact.weights.items():
        for sample in prompts:
            item = items[sample]
            for catalog, known in ((None, Knowledge()), (CATALOG, knowledge)):
                live, _ = router.decide_for(
                    item.question, group=item.task_group, option_count=len(item.options),
                    weights=weights, catalog=catalog,
                )
                assert view.choose(sample, weights, known) == live, (priority, sample)


def _cell(sample: str, model: str, correct: bool, cost: float, latency: float,
          served: bool = True) -> Cell:
    return Cell(sample_id=sample, model_id=model, task_group=TaskGroup.MATH,
                router_split=RouterSplit.FINAL, correct=correct, served=served,
                latency_ms=latency, completion_tokens=10, cost_usd=cost)


def test_world_scenarios_rescale_and_inject_nested_failures() -> None:
    cells = [_cell(f"s{n}", "m", True, 0.01, 1000.0) for n in range(200)]
    cells += [_cell("s0", "mercury-3", False, 0.0, 300.0, served=False)]
    world = World(cells, retired_call_latency(cells))
    assert world.retired_latency_ms == 300.0
    pricey = ScenarioSpec(scenario_id="p", title="t", condition="price", observed=False,
                          description="d", price_multipliers={"m": 4.0},
                          latency_multipliers={"m": 2.0})
    assert world.outcome("s1", "m", pricey) == (True, 0.04, 2000.0, True)
    small = ScenarioSpec(scenario_id="a", title="t", condition="reliability", observed=False,
                         description="d", failure_shares={"m": 0.2})
    large = small.model_copy(update={"failure_shares": {"m": 0.6}})
    failed_small = {f"s{n}" for n in range(200) if not world.outcome(f"s{n}", "m", small)[0]}
    failed_large = {f"s{n}" for n in range(200) if not world.outcome(f"s{n}", "m", large)[0]}
    assert failed_small < failed_large
    assert 20 < len(failed_small) < 60 and 90 < len(failed_large) < 150
    assert all(0 <= _unit_hash("m", f"s{n}") < 1 for n in range(50))
    gone = ScenarioSpec(scenario_id="g", title="t", condition="availability", observed=True,
                        description="d", unavailable=["m"])
    assert world.outcome("s1", "m", gone) == (False, 0.0, 300.0, False)
    real = gone.model_copy(update={"world_already_changed": True})
    assert world.outcome("s1", "m", real) == (True, 0.01, 1000.0, True)


def test_knowledge_composes_changes() -> None:
    drift = Knowledge(unavailable=frozenset({"mercury"}), price={"gemma": 0.9})
    # A hypothetical change on top of the observed drift multiplies with it.
    pricier = drift.plus(Knowledge(price={"gemma": 30.0, "gemini": 4.0}, failure={"g": 0.5}))
    assert pricier.price == {"gemma": pytest.approx(27.0), "gemini": 4.0}
    assert pricier.unavailable == {"mercury"}
    outage = pricier.plus(Knowledge(failure={"g": 0.5}))
    assert outage.failure == {"g": pytest.approx(0.75)}
    # Undoing the observed drift leaves the router that never heard of it.
    assert drift.minus(drift) == Knowledge()
    assert pricier.minus(drift).price == {"gemma": pytest.approx(30.0), "gemini": 4.0}


def test_error_analysis_counts_under_over_dominated_and_unavoidable() -> None:
    items = {
        sample: SuiteItem(
            sample_id=sample, benchmark=Benchmark.GSM8K, task_group=TaskGroup.MATH,
            dataset="d", source_split="test", revision="r", source_id=sample,
            question=f"What is {sample}?", expected_answer="1", router_split=RouterSplit.FINAL,
        )
        for sample in ("a", "b", "c", "d")
    }
    cells = {
        # a: cheap model wrong, pricey model right -> under-routed
        ("a", "cheap"): _cell("a", "cheap", False, 0.001, 900.0),
        ("a", "pricey"): _cell("a", "pricey", True, 0.01, 1000.0),
        # b: pricey right, cheap also right, faster and cheaper -> over-routed and dominated
        ("b", "cheap"): _cell("b", "cheap", True, 0.001, 500.0),
        ("b", "pricey"): _cell("b", "pricey", True, 0.01, 1000.0),
        # c: nobody right -> unavoidable
        ("c", "cheap"): _cell("c", "cheap", False, 0.001, 500.0),
        ("c", "pricey"): _cell("c", "pricey", False, 0.01, 1000.0),
        # d: pricey right, cheap right but slower -> over-routed, not dominated
        ("d", "cheap"): _cell("d", "cheap", True, 0.001, 5000.0),
        ("d", "pricey"): _cell("d", "pricey", True, 0.01, 1000.0),
    }
    picks = {"a": "cheap", "b": "pricey", "c": "pricey", "d": "pricey"}
    oracle = {"a": "pricey", "b": "cheap", "c": "cheap", "d": "cheap"}
    result = errors.analyze(
        "learned:test", picks, oracle, cells,
        lambda sample, model: 0.001 if model == "cheap" else 0.01,
        lambda sample, model: 0.9, items, ["cheap", "pricey"],
        {"cheap": "Cheap", "pricey": "Pricey"},
    )
    overall = result.overall
    assert (overall.correct, overall.wrong, overall.unavoidable) == (2, 2, 1)
    assert (overall.under_routed, overall.over_routed, overall.over_routed_dominated) == (1, 2, 1)
    assert overall.over_routing_extra_cost_usd == pytest.approx(0.018)
    assert (overall.oracle_correct, overall.regret_correct) == (3, 1)
    kinds = [example.kind for example in result.examples]
    assert kinds.count("under") == 1 and kinds.count("over") == 2
    assert "predicted 90% success for Cheap" in result.examples[0].explanation


def test_cost_ratio_interval_skips_resamples_with_a_free_baseline() -> None:
    a = stats.Outcomes.from_rows([(True, 0.01, 1.0)] * 9 + [(True, 0.0, 1.0)])
    b = stats.Outcomes.from_rows([(True, 0.0, 1.0)] * 9 + [(True, 0.02, 1.0)])
    result = stats.compare("a", "b", "q", a, b, stats.bootstrap_indices(10))
    assert result.cost_ratio == pytest.approx(4.5)
    assert result.cost_ratio_ci is not None


def test_final_evaluation_refuses_an_unfinished_run(monkeypatch) -> None:
    from app.learned import final_eval

    suites = final_eval.load_suites()
    partial = suites["final"]
    partial.cells = [cell for cell in partial.cells if cell.sample_id < "mbpp"]
    monkeypatch.setattr(final_eval, "load_suites", lambda: {**suites, "final": partial})
    with pytest.raises(final_eval.IncompleteRunError):
        final_eval.build_report()
