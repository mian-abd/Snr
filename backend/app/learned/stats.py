"""Uncertainty for routing results (proposal, week of Nov 19): intervals and paired tests.

Every strategy is evaluated on the same prompts, so comparisons are paired:

- 95% intervals come from a percentile bootstrap over prompts with 10,000 resamples. One set of
  resampled prompt indices is shared by every strategy, so differences are resampled jointly.
- Correctness differences use McNemar's exact test, which only counts the prompts where exactly
  one of the two strategies is right.
- Cost and latency differences use the same paired bootstrap.
- p-values are Holm-adjusted within each evaluation's fixed family of comparisons.

The seed is fixed, so the numbers are reproducible.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.domain.models import Interval, PairedComparison, StrategyUncertainty

BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20261119
CONFIDENCE = 0.95


@dataclass(frozen=True)
class Outcomes:
    """One strategy's per-prompt results, aligned to a shared prompt order."""

    correct: np.ndarray  # bool
    cost: np.ndarray  # USD
    latency: np.ndarray  # ms

    @classmethod
    def from_rows(cls, rows: Sequence[tuple[bool, float, float]]) -> Outcomes:
        return cls(
            correct=np.array([row[0] for row in rows], dtype=bool),
            cost=np.array([row[1] for row in rows], dtype=float),
            latency=np.array([row[2] for row in rows], dtype=float),
        )


def bootstrap_indices(
    prompts: int, samples: int = BOOTSTRAP_SAMPLES, seed: int = BOOTSTRAP_SEED
) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, prompts, size=(samples, prompts))


def _interval(values: np.ndarray) -> Interval:
    tail = (1 - CONFIDENCE) / 2 * 100
    low, high = np.percentile(values, [tail, 100 - tail])
    return Interval(low=round(float(low), 10), high=round(float(high), 10))


def uncertainty(strategy_id: str, outcomes: Outcomes, indices: np.ndarray) -> StrategyUncertainty:
    return StrategyUncertainty(
        strategy_id=strategy_id,
        accuracy=_interval(outcomes.correct[indices].mean(axis=1)),
        total_cost_usd=_interval(outcomes.cost[indices].sum(axis=1)),
        median_latency_ms=_interval(np.median(outcomes.latency[indices], axis=1)),
    )


def mcnemar_exact(only_first: int, only_second: int) -> float:
    """Two-sided exact McNemar p-value: a binomial test on the discordant prompts."""
    discordant = only_first + only_second
    if discordant == 0:
        return 1.0
    smaller = min(only_first, only_second)
    tail = sum(math.comb(discordant, k) for k in range(smaller + 1)) / 2**discordant
    return float(min(1.0, 2 * tail))


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm's step-down adjustment; returns adjusted p-values in the input order."""
    order = sorted(range(len(p_values)), key=lambda index: p_values[index])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def compare(
    strategy_id: str,
    baseline_id: str,
    question: str,
    strategy: Outcomes,
    baseline: Outcomes,
    indices: np.ndarray,
) -> PairedComparison:
    """One paired comparison; ``holm_p`` is filled in by ``adjust``."""
    only_strategy = int(np.sum(strategy.correct & ~baseline.correct))
    only_baseline = int(np.sum(~strategy.correct & baseline.correct))
    accuracy_difference = strategy.correct.astype(float) - baseline.correct.astype(float)
    cost_difference = strategy.cost - baseline.cost
    baseline_cost = baseline.cost[indices].sum(axis=1)
    ratio = None
    ratio_interval = None
    if baseline.cost.sum() > 0:
        ratio = float(strategy.cost.sum() / baseline.cost.sum())
        paid = baseline_cost > 0  # a resample of only free baseline calls has no ratio
        if paid.any():
            ratio_interval = _interval(
                strategy.cost[indices].sum(axis=1)[paid] / baseline_cost[paid]
            )
    p_value = mcnemar_exact(only_strategy, only_baseline)
    return PairedComparison(
        strategy_id=strategy_id,
        baseline_id=baseline_id,
        question=question,
        prompts=len(strategy.correct),
        correct=int(strategy.correct.sum()),
        baseline_correct=int(baseline.correct.sum()),
        only_strategy_correct=only_strategy,
        only_baseline_correct=only_baseline,
        accuracy_difference=float(accuracy_difference.mean()),
        accuracy_difference_ci=_interval(accuracy_difference[indices].mean(axis=1)),
        mcnemar_p=p_value,
        holm_p=p_value,
        cost_difference_usd=round(float(cost_difference.sum()), 8),
        cost_difference_ci=_interval(cost_difference[indices].sum(axis=1)),
        cost_ratio=None if ratio is None else round(ratio, 6),
        cost_ratio_ci=ratio_interval,
        median_latency_difference_ms=round(
            float(np.median(strategy.latency) - np.median(baseline.latency)), 1
        ),
        median_latency_difference_ci=_interval(
            np.median(strategy.latency[indices], axis=1)
            - np.median(baseline.latency[indices], axis=1)
        ),
    )


def adjust(comparisons: list[PairedComparison]) -> list[PairedComparison]:
    adjusted = holm([item.mcnemar_p for item in comparisons])
    return [
        item.model_copy(update={"holm_p": round(value, 10)})
        for item, value in zip(comparisons, adjusted, strict=True)
    ]
