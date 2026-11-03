"""Offline routing replay and weight tuning over the saved benchmark matrix.

Each strategy routes every prompt to one model, and the outcome is that model's saved cell, so
nothing here calls a provider (proposal: "changing router weights, features, or algorithms can be
tested against the stored results without calling every model again").

Weight presets are tuned on the validation split only, with accuracy floors anchored to the
proposal's baselines so that no preset is worse than simply always using the cheapest model:
- higher quality: the weights with the most correct answers (then lowest cost);
- lower cost / faster response: the cheapest / fastest weights with at least as many correct
  answers as the always-cheapest baseline;
- balanced: with at least as many correct answers as halfway between that baseline and the
  quality preset, the smallest equal-weight sum of the accuracy shortfall from the quality
  preset (relative to the baseline's), normalized cost, and normalized median latency.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Callable
from statistics import median
from typing import Any

from app.benchmarks.suite import RouterSplit, SuiteItem, TaskGroup
from app.domain.models import (
    LearnedStrategyOutcome,
    RoutingPriority,
    RoutingWeights,
    StrategyTaskOutcome,
    WeightTuningResult,
)
from app.learned.features import Cell
from app.learned.router import TaskEstimate, policy_weights
from app.routing.multi_objective import CandidateEstimate, PolicyWeights, choose
from app.routing.policy import effort_score, prompt_signals

# Rule-router roles for this pool, mirroring the Checkpoint 2 paid policy.
CHEAPEST, FASTEST, STRONGEST = "gemma-4-26b", "mercury-3", "gemini-4-argon"
EMPHASIS_GRID = (0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
SECONDARY_GRID = (0.0, 0.02, 0.05)
RELIABILITY_GRID = (0.0, 0.5)
NO_LATENCY_MS = 60000.0  # assumed when a model never served a call in a task group

Outcome = tuple[bool, float, float]  # correct, cost in USD, latency in ms
Chooser = Callable[[str], str]  # sample_id -> model_id


def summarize(outcomes: list[Outcome]) -> dict[str, Any]:
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


def routing_estimates(
    cells: list[Cell], splits: frozenset[RouterSplit]
) -> dict[str, dict[TaskGroup, TaskEstimate]]:
    """Mean cost, median served latency, and failure rate per model and task group."""
    grouped: dict[tuple[str, TaskGroup], list[Cell]] = defaultdict(list)
    for cell in cells:
        if cell.router_split in splits:
            grouped[(cell.model_id, cell.task_group)].append(cell)
    estimates: dict[str, dict[TaskGroup, TaskEstimate]] = defaultdict(dict)
    for (model_id, group), members in grouped.items():
        served = [cell.latency_ms for cell in members if cell.served]
        estimates[model_id][group] = TaskEstimate(
            expected_cost_usd=sum(cell.cost_usd for cell in members) / len(members),
            expected_latency_ms=median(served) if served else NO_LATENCY_MS,
            failure_rate=sum(1 for cell in members if not cell.served) / len(members),
        )
    return dict(estimates)


def complete_prompts(cells: list[Cell], split: RouterSplit, models: list[str]) -> list[str]:
    """Prompts of one split that every model answered (failed calls count as answered)."""
    seen: dict[str, set[str]] = defaultdict(set)
    for cell in cells:
        if cell.router_split == split:
            seen[cell.sample_id].add(cell.model_id)
    return sorted(sample for sample, answered in seen.items() if set(models) <= answered)


def replay(
    prompts: list[str],
    choosers: dict[str, Chooser],
    cells: list[Cell],
    items: dict[str, SuiteItem],
) -> list[LearnedStrategyOutcome]:
    by_key = {(cell.sample_id, cell.model_id): cell for cell in cells}
    results = []
    for name, chooser in choosers.items():
        outcomes: list[Outcome] = []
        by_task: dict[TaskGroup, list[Outcome]] = defaultdict(list)
        picks: Counter[str] = Counter()
        for sample_id in prompts:
            model_id = chooser(sample_id)
            cell = by_key[(sample_id, model_id)]
            outcome = (cell.correct, cell.cost_usd, cell.latency_ms)
            outcomes.append(outcome)
            by_task[items[sample_id].task_group].append(outcome)
            picks[model_id] += 1
        task_outcomes = {}
        for group in TaskGroup:
            if by_task[group]:
                summary = summarize(by_task[group])
                task_outcomes[group.value] = StrategyTaskOutcome(
                    prompts=summary["prompts"],
                    correct=summary["correct"],
                    accuracy=summary["accuracy"],
                    total_cost_usd=summary["total_cost_usd"],
                    median_latency_ms=summary["median_latency_ms"],
                )
        results.append(
            LearnedStrategyOutcome(
                strategy_id=name,
                **summarize(outcomes),
                selected_models=dict(picks.most_common()),
                by_task=task_outcomes,
            )
        )
    return results


def fixed_and_rule_choosers(items: dict[str, SuiteItem], models: list[str]) -> dict[str, Chooser]:
    if not {CHEAPEST, FASTEST, STRONGEST} <= set(models):
        return {}

    def rule(sample_id: str) -> str:
        score = effort_score(prompt_signals(items[sample_id].question))
        return STRONGEST if score >= 3 else FASTEST if score else CHEAPEST

    return {
        "fixed_cheapest": lambda _: CHEAPEST,
        "fixed_strongest": lambda _: STRONGEST,
        "rule_balanced": rule,
    }


def score_chooser(
    probability: Callable[[str, str], float],
    estimates: dict[str, dict[TaskGroup, TaskEstimate]],
    models: list[str],
    items: dict[str, SuiteItem],
    weights: PolicyWeights,
) -> Chooser:
    def pick(sample_id: str) -> str:
        group = items[sample_id].task_group
        candidates = [
            CandidateEstimate(
                model_id=model_id,
                p_success=probability(sample_id, model_id),
                expected_cost_usd=estimates[model_id][group].expected_cost_usd,
                expected_latency_ms=estimates[model_id][group].expected_latency_ms,
                failure_rate=estimates[model_id][group].failure_rate,
            )
            for model_id in sorted(models)
        ]
        return choose(candidates, weights).model_id

    return pick


def weight_grid(priority: RoutingPriority) -> list[RoutingWeights]:
    grid: list[RoutingWeights] = []
    for reliability in RELIABILITY_GRID:
        if priority == RoutingPriority.QUALITY:
            grid += [
                RoutingWeights(cost=cost, latency=latency, reliability=reliability)
                for cost in SECONDARY_GRID
                for latency in SECONDARY_GRID
            ]
        elif priority == RoutingPriority.COST:
            grid += [
                RoutingWeights(cost=cost, latency=latency, reliability=reliability)
                for cost in EMPHASIS_GRID
                for latency in SECONDARY_GRID
            ]
        elif priority == RoutingPriority.LATENCY:
            grid += [
                RoutingWeights(cost=cost, latency=latency, reliability=reliability)
                for latency in EMPHASIS_GRID
                for cost in SECONDARY_GRID
            ]
        else:
            grid += [
                RoutingWeights(cost=cost, latency=latency, reliability=reliability)
                for cost in EMPHASIS_GRID
                for latency in EMPHASIS_GRID
            ]
    return grid


def tune_weights(
    prompts: list[str],
    probability: Callable[[str, str], float],
    estimates: dict[str, dict[TaskGroup, TaskEstimate]],
    models: list[str],
    cells: list[Cell],
    items: dict[str, SuiteItem],
) -> list[WeightTuningResult]:
    """Choose one preset per priority on the given (validation) prompts."""

    def evaluate(weights: RoutingWeights) -> LearnedStrategyOutcome:
        chooser = score_chooser(probability, estimates, models, items, policy_weights(weights))
        return replay(prompts, {"trial": chooser}, cells, items)[0]

    def key(weights: RoutingWeights) -> tuple[float, ...]:
        return (weights.cost, weights.latency, weights.reliability)

    trials = {
        priority: [(weights, evaluate(weights)) for weights in weight_grid(priority)]
        for priority in RoutingPriority
    }
    quality_weights, quality = min(
        trials[RoutingPriority.QUALITY],
        key=lambda pair: (
            -pair[1].correct, pair[1].total_cost_usd, pair[1].median_latency_ms or 0.0,
            key(pair[0]),
        ),
    )
    chosen: dict[RoutingPriority, tuple[RoutingWeights, LearnedStrategyOutcome, int | None]] = {
        RoutingPriority.QUALITY: (quality_weights, quality, None)
    }
    baseline = (
        replay(prompts, {"cheapest": lambda _: CHEAPEST}, cells, items)[0].correct
        if CHEAPEST in models
        else 0
    )
    floors = {
        RoutingPriority.COST: baseline,
        RoutingPriority.LATENCY: baseline,
        RoutingPriority.BALANCED: math.ceil((baseline + quality.correct) / 2),
    }
    for priority in (RoutingPriority.COST, RoutingPriority.LATENCY, RoutingPriority.BALANCED):
        floor = floors[priority]
        feasible = [pair for pair in trials[priority] if pair[1].correct >= floor]
        feasible = feasible or trials[priority]
        if priority == RoutingPriority.COST:
            best = min(
                feasible,
                key=lambda pair: (
                    pair[1].total_cost_usd, -pair[1].correct, pair[1].median_latency_ms or 0.0,
                    key(pair[0]),
                ),
            )
        elif priority == RoutingPriority.LATENCY:
            best = min(
                feasible,
                key=lambda pair: (
                    pair[1].median_latency_ms or 0.0, -pair[1].correct, pair[1].total_cost_usd,
                    key(pair[0]),
                ),
            )
        else:
            top_cost = max(pair[1].total_cost_usd for pair in feasible) or 1.0
            top_latency = max(pair[1].median_latency_ms or 0.0 for pair in feasible) or 1.0
            spread = max(quality.correct - baseline, 1)
            best = min(
                feasible,
                key=lambda pair: (
                    (quality.correct - pair[1].correct) / spread
                    + pair[1].total_cost_usd / top_cost
                    + (pair[1].median_latency_ms or 0.0) / top_latency,
                    -pair[1].correct,
                    key(pair[0]),
                ),
            )
        chosen[priority] = (best[0], best[1], floor)
    return [
        WeightTuningResult(
            priority=priority,
            weights=weights,
            validation_correct=outcome.correct,
            validation_cost_usd=outcome.total_cost_usd,
            validation_median_latency_ms=outcome.median_latency_ms,
            accuracy_floor=floor,
            candidates_tried=len(trials[priority]),
        )
        for priority in RoutingPriority
        for weights, outcome, floor in [chosen[priority]]
    ]
