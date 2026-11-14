"""The final held-out evaluation of the frozen learned router (proposal, week of Nov 19).

    uv run --project backend python -m app.learned.final_eval --from-runs   # rebuild the table
    uv run --project backend python -m app.learned.final_eval               # from the table

Nothing is trained or tuned here. The router is ``data/learned/cp3-router-model.json`` exactly
as Checkpoint 3 exported it. Two evaluations use it:

1. The Checkpoint 3 test split (120 prompts), re-read with uncertainty added. Its strategy
   results must reproduce the Checkpoint 3 report, which this script checks.
2. The final set (300 prompts drawn after the router was frozen; ``prepare_final``), answered
   by the pool on 2026-11-13. By then OpenRouter had retired Mercury 3 and cut Gemma 4 26B's
   price, so the deployed router applies the live catalog saved that day. The same router
   without the catalog shows what the drift would have cost.

Each evaluation reports the baselines, the rule router, the learned presets, a model-by-task
reference, the oracle, bootstrap intervals, a fixed family of paired tests, the routing-error
analysis, and the robustness scenarios. ``--from-runs`` first rebuilds the committed cell table
``data/learned/cells.jsonl`` (outcomes only, no response text) from the raw local runs; without
it, a clone of the repository reproduces the report from committed files alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from app.benchmarks.suite import RouterSplit, SuiteItem, TaskGroup, load_suite
from app.benchmarks.suite_runner import FINAL_PATH, RUNS_DIR, SUITE_PATH
from app.config import REPOSITORY_ROOT
from app.domain.models import (
    ClassifierMetrics,
    EvaluationSet,
    FinalEvaluationReport,
    LearnedRouterReport,
    LearnedStrategyOutcome,
    LiveCatalogStatus,
    RoutingPriority,
)
from app.learned import errors, stats
from app.learned.evaluate import replay
from app.learned.features import Cell
from app.learned.plots import write_pair
from app.learned.robustness import (
    BASELINES,
    Knowledge,
    RouterView,
    World,
    _oracle_choice,
    catalog_knowledge,
    retired_call_latency,
    run_scenarios,
    standard_scenarios,
)
from app.learned.router import ROUTER_MODEL_PATH, LearnedRouter, load_router
from app.learned.train import POOL_PATH, _metrics, matrix_summary
from app.registry.pool import load_pool
from app.storage import atomic_write_json, atomic_write_jsonl, read_jsonl

LEARNED_DIR = REPOSITORY_ROOT / "data" / "learned"
CELLS_PATH = LEARNED_DIR / "cells.jsonl"
DECISIONS_PATH = LEARNED_DIR / "final-decisions.jsonl"
REPORT_PATH = LEARNED_DIR / "final-evaluation.json"
CP3_REPORT_PATH = LEARNED_DIR / "cp3-full-router-comparison.json"
CATALOG_PATH = REPOSITORY_ROOT / "data" / "registry" / "live-catalog-2026-11-13.json"
FIGURE_DIR = REPOSITORY_ROOT / "docs" / "figures"
RUN_IDS = {"cp3": "cp3-full", "final": "final-heldout"}

# Fixed before the final set's results were read. Each tuple: strategy, baseline, question.
COMPARISONS: list[tuple[str, str, str]] = [
    ("learned:quality", "fixed_strongest",
     "Is the best-quality setting as accurate as always using the strongest model, for less?"),
    ("learned:cost", "fixed_cheapest",
     "Is the lowest-cost setting as accurate as always using the cheapest paid model, for less?"),
    ("learned:latency", "rule_balanced",
     "Is the fastest setting quicker than the rule-based router without losing accuracy?"),
    ("learned:balanced", "rule_balanced",
     "Does the balanced setting beat the rule-based router?"),
    ("learned:quality", "model_task_prior:quality",
     "Do the prompt features add accuracy beyond per-task averages?"),
    ("learned:cost", "model_task_prior:cost",
     "Do the prompt features help the lowest-cost setting beyond per-task averages?"),
]
DRIFT_COMPARISONS: list[tuple[str, str, str]] = [
    ("learned:latency", "learned_no_catalog:latency",
     "How much does the live catalog check protect the fastest setting from the retired "
     "model?"),
    ("learned:balanced", "learned_no_catalog:balanced",
     "How much does the live catalog check protect the balanced setting?"),
]


@dataclass
class Suite:
    name: str
    items: dict[str, SuiteItem]
    cells: list[Cell]


def _cell_row(suite: str, item: SuiteItem, row: dict[str, Any], correct: bool) -> dict[str, Any]:
    result = row["result"]
    return {
        "suite": suite,
        "sample_id": item.sample_id,
        "benchmark": item.benchmark.value,
        "task_group": item.task_group.value,
        "router_split": item.router_split.value,
        "model_id": row["model_id"],
        "status": result["status"],
        "correct": correct,
        "latency_ms": round(float(result["latency_ms"]), 3),
        "cost_usd": float(result.get("cost_usd") or 0.0),
        "completion_tokens": result.get("completion_tokens"),
    }


def build_cell_table() -> dict[str, Any]:
    """Collect scored outcomes from the raw local runs into one committed, text-free table."""
    rows: list[dict[str, Any]] = []
    spend: dict[str, float] = {}
    for suite, path in (("cp3", SUITE_PATH), ("final", FINAL_PATH)):
        items = {item.sample_id: item for item in load_suite(path)}
        run_dir = RUNS_DIR / RUN_IDS[suite]
        code_scores = {
            (score["model_id"], score["sample_id"]): bool(score["passed"])
            for score_path in run_dir.glob("*/code_scores.jsonl")
            for score in read_jsonl(score_path)
        }
        for results in sorted(run_dir.glob("*/results.jsonl")):
            for row in read_jsonl(results):
                item = items.get(row["sample_id"])
                if item is None:
                    continue
                correct = row["correct"]
                if correct is None:
                    correct = code_scores.get((row["model_id"], row["sample_id"]))
                if correct is None:
                    continue  # code awaiting EvalPlus
                rows.append(_cell_row(suite, item, row, bool(correct)))
        spend[suite] = float(sum(
            (
                Decimal(str(attempt["result"].get("cost_usd") or "0"))
                for attempts in run_dir.glob("*/attempts.jsonl")
                for attempt in read_jsonl(attempts)
            ),
            Decimal("0"),
        ))
    rows.sort(key=lambda row: (row["suite"], row["sample_id"], row["model_id"]))
    atomic_write_jsonl(CELLS_PATH, rows)
    meta = {
        "rows": len(rows),
        "rows_by_suite": dict(Counter(row["suite"] for row in rows)),
        "provider_billed_spend_usd": {key: round(value, 6) for key, value in spend.items()},
        "cells_sha256": _sha256(CELLS_PATH),
        "note": "Scored outcomes only: no prompts, responses, or request IDs. Prompts are in "
        "data/benchmarks; failed calls count as wrong.",
    }
    atomic_write_json(CELLS_PATH.with_suffix(".meta.json"), meta)
    return meta


def load_suites() -> dict[str, Suite]:
    suites = {
        "cp3": Suite("cp3", {item.sample_id: item for item in load_suite(SUITE_PATH)}, []),
        "final": Suite("final", {item.sample_id: item for item in load_suite(FINAL_PATH)}, []),
    }
    for row in read_jsonl(CELLS_PATH):
        suite = suites[row["suite"]]
        item = suite.items[row["sample_id"]]
        suite.cells.append(Cell(
            sample_id=item.sample_id,
            model_id=row["model_id"],
            task_group=item.task_group,
            router_split=item.router_split,
            correct=bool(row["correct"]),
            served=row["status"] == "success",
            latency_ms=float(row["latency_ms"]),
            completion_tokens=row["completion_tokens"],
            cost_usd=float(row["cost_usd"]),
        ))
    return suites


def complete(cells: list[Cell], split: RouterSplit, models: list[str]) -> list[str]:
    answered: dict[str, set[str]] = defaultdict(set)
    for cell in cells:
        if cell.router_split == split:
            answered[cell.sample_id].add(cell.model_id)
    return sorted(sample for sample, seen in answered.items() if set(models) <= seen)


def _lookup(chosen: dict[str, str]) -> Callable[[str], str]:
    return chosen.__getitem__


def _outcomes(picks: dict[str, str], world: World, prompts: list[str]) -> stats.Outcomes:
    return stats.Outcomes.from_rows(
        [world.outcome(sample, picks[sample])[:3] for sample in prompts]
    )


class IncompleteRunError(RuntimeError):
    pass


def evaluate_set(
    evaluation_id: str,
    title: str,
    description: str,
    router: LearnedRouter,
    suite: Suite,
    split: RouterSplit,
    base: Knowledge,
    comparisons: list[tuple[str, str, str]],
    retired_latency_ms: float,
    allow_partial: bool = False,
) -> tuple[EvaluationSet, dict[str, dict[str, str]], RouterView, World, list[str]]:
    models = router.pool_ids
    prompts = complete(suite.cells, split, models)
    expected = sum(item.router_split == split for item in suite.items.values())
    if len(prompts) < expected and not allow_partial:
        raise IncompleteRunError(
            f"{evaluation_id}: only {len(prompts)} of {expected} prompts have a scored outcome "
            "from every model (unfinished runs, or code awaiting EvalPlus). Finish them, or "
            "pass --allow-partial for a provisional report."
        )
    cells = [cell for cell in suite.cells if cell.sample_id in set(prompts)]
    world = World(cells, retired_latency_ms)
    view = RouterView(router, suite.items, prompts)
    prior = RouterView(router, suite.items, prompts)
    prior.p = {
        (sample, model_id): router.history.success_rate(
            model_id, suite.items[sample].task_group, None
        )
        for sample in prompts
        for model_id in models
    }
    presets = router.artifact.weights
    picks: dict[str, dict[str, str]] = {}
    for name, choose in BASELINES.items():
        picks[name] = {sample: choose(suite.items[sample], base.unavailable) for sample in prompts}
    if base.unavailable:
        # The Checkpoint 2 rule router has no catalog check of its own; offline it would still
        # call its pinned models (live, its route refuses to run at all).
        picks["rule_balanced_no_catalog"] = {
            sample: BASELINES["rule_balanced"](suite.items[sample], frozenset())
            for sample in prompts
        }
    for priority in RoutingPriority:
        weights = presets[priority]
        picks[f"learned:{priority.value}"] = {
            sample: view.choose(sample, weights, base) for sample in prompts
        }
        if base.unavailable or base.price:
            picks[f"learned_no_catalog:{priority.value}"] = {
                sample: view.choose(sample, weights, Knowledge()) for sample in prompts
            }
        picks[f"model_task_prior:{priority.value}"] = {
            sample: prior.choose(sample, weights, base) for sample in prompts
        }
    oracle_picks = {
        f"oracle:{priority.value}": {
            sample: _oracle_choice(world, sample, models, presets[priority], None,
                                   base.unavailable)
            for sample in prompts
        }
        for priority in RoutingPriority
    }
    choosers = {name: _lookup(chosen) for name, chosen in picks.items()}
    oracle_choosers = {name: _lookup(chosen) for name, chosen in oracle_picks.items()}
    strategies = replay(prompts, choosers, cells, suite.items)
    oracle = replay(prompts, oracle_choosers, cells, suite.items)
    indices = stats.bootstrap_indices(len(prompts))
    every = {**picks, **oracle_picks}
    outcomes = {name: _outcomes(chosen, world, prompts) for name, chosen in every.items()}
    uncertainty = [stats.uncertainty(name, outcome, indices) for name, outcome in outcomes.items()]
    paired = stats.adjust([
        stats.compare(strategy, baseline, question, outcomes[strategy], outcomes[baseline],
                      indices)
        for strategy, baseline, question in comparisons
        if strategy in outcomes and baseline in outcomes
    ])
    available = [model for model in models if model not in base.unavailable]
    cell_map = {(cell.sample_id, cell.model_id): cell for cell in cells}

    def expected_cost(sample: str, model_id: str) -> float:
        estimate = router.artifact.estimates[model_id][suite.items[sample].task_group]
        return estimate.expected_cost_usd * base.price.get(model_id, 1.0)

    names = {model_id: router.models[model_id].display_name for model_id in models}
    routing_errors = [
        errors.analyze(
            f"learned:{priority.value}", picks[f"learned:{priority.value}"],
            oracle_picks[f"oracle:{priority.value}"], cell_map, expected_cost,
            lambda sample, model_id: view.p[(sample, model_id)], suite.items, available, names,
        )
        for priority in RoutingPriority
    ]
    scored = [
        (cell, view.p[(cell.sample_id, cell.model_id)], prior.p[(cell.sample_id, cell.model_id)])
        for cell in cells
        if cell.model_id not in base.unavailable
    ]
    labels = np.array([int(cell.correct) for cell, _, _ in scored])
    by_task = Counter(suite.items[sample].task_group.value for sample in prompts)
    evaluation = EvaluationSet(
        evaluation_id=evaluation_id,
        title=title,
        description=description,
        prompts=len(prompts),
        prompts_by_task={group.value: by_task[group.value] for group in TaskGroup},
        models=models,
        catalog_applied=bool(base.unavailable or base.price),
        classifier=ClassifierMetrics.model_validate(
            _metrics(labels, np.array([p for _, p, _ in scored]))
        ),
        reference_model_task_prior=ClassifierMetrics.model_validate(
            _metrics(labels, np.array([p for _, _, p in scored]))
        ),
        matrix=matrix_summary(cells, router.models),
        strategies=strategies,
        oracle=oracle,
        uncertainty=uncertainty,
        comparisons=paired,
        routing_errors=routing_errors,
    )
    return evaluation, {**picks, **oracle_picks}, view, world, prompts


def check_cp3_parity(evaluation: EvaluationSet) -> None:
    """The Checkpoint 3 test results must come out exactly as reported at Checkpoint 3."""
    report = LearnedRouterReport.model_validate_json(CP3_REPORT_PATH.read_text(encoding="utf-8"))
    reported = {
        item.strategy_id: item for item in report.heldout.strategies + report.heldout.oracle
    }
    for strategy in evaluation.strategies + evaluation.oracle:
        before = reported.get(strategy.strategy_id)
        if before is None:
            continue
        if (before.correct, round(before.total_cost_usd, 6)) != (
            strategy.correct, round(strategy.total_cost_usd, 6)
        ):
            raise RuntimeError(f"{strategy.strategy_id} no longer reproduces Checkpoint 3")
    if evaluation.prompts != report.heldout.prompts:
        raise RuntimeError("The Checkpoint 3 test prompt count changed")
    if abs(evaluation.classifier.log_loss - report.heldout.classifier.log_loss) > 1e-9:
        raise RuntimeError("The classifier's test log loss no longer reproduces Checkpoint 3")


def decision_rows(
    evaluation_id: str,
    picks: dict[str, dict[str, str]],
    world: World,
    items: dict[str, SuiteItem],
    prompts: list[str],
) -> list[dict[str, Any]]:
    rows = []
    for strategy, chosen in picks.items():
        for sample in prompts:
            correct, cost, latency, served = world.outcome(sample, chosen[sample])
            rows.append({
                "evaluation": evaluation_id,
                "sample_id": sample,
                "benchmark": items[sample].benchmark.value,
                "task_group": items[sample].task_group.value,
                "strategy": strategy,
                "model_id": chosen[sample],
                "correct": correct,
                "served": served,
                "cost_usd": cost,
                "latency_ms": latency,
            })
    return rows


def _sha256(path: Path) -> str:
    """SHA-256 of a committed text file with LF line endings, so every checkout agrees.

    Git stores these files with LF; a Windows checkout may write CRLF.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build_report(allow_partial: bool = False) -> tuple[FinalEvaluationReport, list[dict[str, Any]]]:
    pool = load_pool(POOL_PATH)
    router = load_router(ROUTER_MODEL_PATH, pool)
    catalog = LiveCatalogStatus.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))
    drift = catalog_knowledge(catalog)
    suites = load_suites()
    # Mercury's final-set calls are real 404s from the retired model; both worlds use their speed.
    retired_ms = retired_call_latency(suites["final"].cells)
    cp3, cp3_picks, cp3_view, cp3_world, cp3_prompts = evaluate_set(
        "cp3_test",
        "Original test split",
        "The 120 held-out test prompts of the 600-prompt suite the router was built on, "
        "answered in late October before the provider changes.",
        router, suites["cp3"], RouterSplit.TEST, Knowledge(), COMPARISONS, retired_ms,
    )
    check_cp3_parity(cp3)
    final_count = len(suites["final"].items)
    final, final_picks, final_view, final_world, final_prompts = evaluate_set(
        "final",
        "Fresh prompts",
        f"{final_count} fresh prompts drawn after the router was frozen and answered on "
        "2026-11-13 and 14. Mercury 3 had been retired, so its calls failed; the router "
        "applies the live catalog saved on 2026-11-13.",
        router, suites["final"], RouterSplit.FINAL, drift, COMPARISONS + DRIFT_COMPARISONS,
        retired_ms, allow_partial,
    )
    if len(final_prompts) < final_count:
        final = final.model_copy(update={
            "title": "Fresh prompts (provisional)",
            "description": f"PROVISIONAL: {len(final_prompts)} of {final_count} prompts so far. "
            + final.description,
        })
    mercury_calls = sum(
        1 for cell in suites["final"].cells if cell.model_id == "mercury-3" and not cell.served
    )
    gemma_ratio = drift.price.get("gemma-4-26b", 1.0)
    robustness = [
        run_scenarios(
            "cp3_test", cp3_view, cp3_world, cp3_prompts, router.pool_ids,
            standard_scenarios(router.pool_ids, gemma_price_ratio=gemma_ratio,
                               drift_in_world=False),
            Knowledge(),
            ["Outcomes are the stored late-October calls; every scenario rescales them."],
        ),
        run_scenarios(
            "final", final_view, final_world, final_prompts, router.pool_ids,
            standard_scenarios(router.pool_ids, gemma_price_ratio=gemma_ratio,
                               drift_in_world=True),
            drift,
            ["The stored calls already include the observed drift (Mercury's calls failed and "
             "Gemma was billed at the new price), so that scenario changes only what the "
             "router knows.",
             "Hypothetical scenarios apply on top of the live catalog of 2026-11-13."],
        ),
    ]
    meta = json.loads(CELLS_PATH.with_suffix(".meta.json").read_text(encoding="utf-8"))
    report = FinalEvaluationReport(
        artifact_id=router.artifact.artifact_id,
        artifact_sha256=_sha256(ROUTER_MODEL_PATH),
        final_set_sha256=_sha256(FINAL_PATH),
        pool_snapshot_id=pool.snapshot_id,
        catalog=catalog,
        protocol=[
            f"The router is {ROUTER_MODEL_PATH.relative_to(REPOSITORY_ROOT).as_posix()} as "
            "exported on 2026-11-03; nothing was retrained or retuned for this evaluation.",
            f"The final set's {final_count} prompts were drawn with their own seed from the same "
            "pinned "
            "sources after the router was frozen, excluding all 600 suite prompts and "
            "the 12 GSM8K pilot questions. The file's SHA-256 was recorded before any model "
            "answered it, "
            "and every run manifest repeats it.",
            "The paired comparisons and their questions were fixed in code before the final "
            "results were read. p-values are Holm-adjusted within each evaluation.",
            "Intervals are 95% percentile-bootstrap intervals over prompts (10,000 resamples, "
            "fixed seed). Costs are what the providers billed; free models cost $0.",
            "On the final set the router applies the live catalog saved on 2026-11-13. "
            f"Mercury 3's {mercury_calls} calls really failed, which is what the no-catalog "
            "rows show.",
        ],
        evaluations=[cp3, final],
        robustness=robustness,
        spend_usd=float(meta["provider_billed_spend_usd"]["final"]),
    )
    rows = decision_rows("cp3_test", cp3_picks, cp3_world, suites["cp3"].items, cp3_prompts)
    rows += decision_rows("final", final_picks, final_world, suites["final"].items, final_prompts)
    return report, rows


def write_figures(report: FinalEvaluationReport) -> list[Path]:
    final = next(item for item in report.evaluations if item.evaluation_id == "final")
    subtitle = (
        f"{final.prompts} fresh prompts answered on 2026-11-13. Router {report.artifact_id}, "
        "frozen on 2026-11-03, with the live catalog applied (Mercury 3 retired)."
    )
    return write_pair(
        final.strategies, final.prompts, subtitle, "the final held-out set", "final-heldout",
        FIGURE_DIR,
    )


def summarize(strategies: list[LearnedStrategyOutcome], prefix: str) -> None:
    for strategy in strategies:
        print(f"  {prefix} {strategy.strategy_id:34} {strategy.correct:3}/{strategy.prompts} "
              f"${strategy.total_cost_usd:8.4f}  median {strategy.median_latency_ms} ms")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-runs", action="store_true",
                        help="Rebuild data/learned/cells.jsonl from the raw local runs first")
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Report a provisional evaluation before every model has finished")
    args = parser.parse_args()
    if args.from_runs:
        meta = build_cell_table()
        print(f"cell table: {meta['rows_by_suite']}, spend {meta['provider_billed_spend_usd']}")
    report, rows = build_report(args.allow_partial)
    REPORT_PATH.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    atomic_write_jsonl(DECISIONS_PATH, rows)
    for evaluation in report.evaluations:
        print(f"{evaluation.title}: {evaluation.prompts} prompts, "
              f"log loss {evaluation.classifier.log_loss:.4f} "
              f"(table {evaluation.reference_model_task_prior.log_loss:.4f})")
        summarize(evaluation.strategies + evaluation.oracle, evaluation.evaluation_id)
        for comparison in evaluation.comparisons:
            print(f"  {comparison.strategy_id} vs {comparison.baseline_id}: "
                  f"{comparison.accuracy_difference:+.3f} "
                  f"[{comparison.accuracy_difference_ci.low:+.3f}, "
                  f"{comparison.accuracy_difference_ci.high:+.3f}] "
                  f"Holm p={comparison.holm_p:.3f}, cost ratio {comparison.cost_ratio}")
    if not args.no_figures:
        for path in write_figures(report):
            print(f"wrote {path.relative_to(REPOSITORY_ROOT)}")
    print(f"wrote {REPORT_PATH.relative_to(REPOSITORY_ROOT)} and "
          f"{DECISIONS_PATH.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
