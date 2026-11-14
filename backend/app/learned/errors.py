"""Oracle gap and routing-error analysis with worked examples (proposal, weeks of Nov 12-19).

Proposal: "error analysis that identifies cases where the router selected a model that was
unnecessarily expensive or selected a cheaper model that failed when another model succeeded."
Models are ordered by the router's own expected cost for the prompt's task group (at the live
price when the catalog reported one), so "cheaper" means cheaper as the router saw it. The
stricter dominated count asks whether a cheaper model that was also right was no slower on the
actual call either. Retired models are not counted as alternatives.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.benchmarks.suite import SuiteItem, TaskGroup
from app.domain.models import ErrorBreakdown, ErrorExample, RoutingErrorAnalysis
from app.learned.evaluate import STRONGEST
from app.learned.features import Cell

EXCERPT_CHARS = 220
EXAMPLES_PER_KIND = 2


@dataclass(frozen=True)
class PromptVerdict:
    sample_id: str
    group: TaskGroup
    chosen: str
    correct: bool
    unavoidable: bool
    under: str | None  # the cheapest costlier model that was right
    over: str | None  # the cheapest cheaper model that was also right
    dominated: bool
    extra_cost: float
    oracle_correct: bool
    oracle_cost: float


def excerpt(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= EXCERPT_CHARS else flat[: EXCERPT_CHARS - 1].rstrip() + "…"


def _verdict(
    sample: str,
    chosen: str,
    oracle: str,
    cells: dict[tuple[str, str], Cell],
    expected_cost: Callable[[str, str], float],
    models: list[str],
    group: TaskGroup,
) -> PromptVerdict:
    cell = cells[(sample, chosen)]
    right = [model for model in models if cells[(sample, model)].correct]
    price = {model: expected_cost(sample, model) for model in models}
    chosen_price = expected_cost(sample, chosen)
    under = over = None
    dominated = False
    extra = 0.0
    if not cell.correct:
        costlier = [model for model in right if price[model] > chosen_price]
        if costlier:
            under = min(costlier, key=lambda model: (price[model], model))
    else:
        cheaper = [model for model in right if model != chosen and price[model] < chosen_price]
        if cheaper:
            over = min(cheaper, key=lambda model: (price[model], model))
            dominated = any(
                cells[(sample, model)].cost_usd <= cell.cost_usd
                and cells[(sample, model)].latency_ms <= cell.latency_ms
                for model in cheaper
            )
            extra = cell.cost_usd - min(cells[(sample, model)].cost_usd for model in right)
    oracle_cell = cells[(sample, oracle)]
    return PromptVerdict(
        sample_id=sample, group=group, chosen=chosen, correct=cell.correct,
        unavoidable=not cell.correct and not right, under=under, over=over,
        dominated=dominated, extra_cost=max(extra, 0.0), oracle_correct=oracle_cell.correct,
        oracle_cost=oracle_cell.cost_usd,
    )


def _breakdown(verdicts: list[PromptVerdict], cells: dict[tuple[str, str], Cell]) -> ErrorBreakdown:
    correct = sum(item.correct for item in verdicts)
    oracle_correct = sum(item.oracle_correct for item in verdicts)
    return ErrorBreakdown(
        prompts=len(verdicts),
        correct=correct,
        wrong=len(verdicts) - correct,
        unavoidable=sum(item.unavoidable for item in verdicts),
        under_routed=sum(item.under is not None for item in verdicts),
        over_routed=sum(item.over is not None for item in verdicts),
        over_routed_dominated=sum(item.dominated for item in verdicts),
        over_routing_extra_cost_usd=round(sum(item.extra_cost for item in verdicts), 8),
        total_cost_usd=round(
            sum(cells[(item.sample_id, item.chosen)].cost_usd for item in verdicts), 8
        ),
        oracle_correct=oracle_correct,
        oracle_cost_usd=round(sum(item.oracle_cost for item in verdicts), 8),
        regret_correct=oracle_correct - correct,
    )


def _money(value: float) -> str:
    return "$0 (free)" if value == 0 else f"${value:.5f}"


def analyze(
    strategy_id: str,
    picks: dict[str, str],
    oracle_picks: dict[str, str],
    cells: dict[tuple[str, str], Cell],
    expected_cost: Callable[[str, str], float],
    predicted: Callable[[str, str], float],
    items: dict[str, SuiteItem],
    models: list[str],
    names: dict[str, str],
) -> RoutingErrorAnalysis:
    verdicts = [
        _verdict(sample, picks[sample], oracle_picks[sample], cells, expected_cost, models,
                 items[sample].task_group)
        for sample in sorted(picks)
    ]
    by_task = {
        group.value: _breakdown([item for item in verdicts if item.group == group], cells)
        for group in TaskGroup
        if any(item.group == group for item in verdicts)
    }
    return RoutingErrorAnalysis(
        strategy_id=strategy_id,
        overall=_breakdown(verdicts, cells),
        by_task=by_task,
        examples=_examples(verdicts, cells, predicted, items, names, models),
    )


def _example(
    kind: str,
    item: PromptVerdict,
    alternative: str | None,
    cells: dict[tuple[str, str], Cell],
    predicted: Callable[[str, str], float],
    items: dict[str, SuiteItem],
    names: dict[str, str],
) -> ErrorExample:
    chosen = cells[(item.sample_id, item.chosen)]
    other = cells[(item.sample_id, alternative)] if alternative else None
    p = predicted(item.sample_id, item.chosen)
    chosen_name = names[item.chosen]
    if kind == "under" and other is not None and alternative:
        explanation = (
            f"The router predicted {p:.0%} success for {chosen_name}, which answered wrong. "
            f"{names[alternative]}, which the router expected to cost more, answered right for "
            f"{_money(other.cost_usd)} in {other.latency_ms / 1000:.1f} s."
        )
    elif kind == "over" and other is not None and alternative:
        explanation = (
            f"{chosen_name} answered right for {_money(chosen.cost_usd)} in "
            f"{chosen.latency_ms / 1000:.1f} s, but {names[alternative]}, which the router "
            f"expected to cost less, was also right for {_money(other.cost_usd)} in "
            f"{other.latency_ms / 1000:.1f} s."
        )
    else:
        assert other is not None and alternative
        verdict = "also right" if other.correct else "wrong"
        explanation = (
            f"{chosen_name} answered right for {_money(chosen.cost_usd)} in "
            f"{chosen.latency_ms / 1000:.1f} s. Always using {names[alternative]} would have "
            f"cost {_money(other.cost_usd)} and taken {other.latency_ms / 1000:.1f} s, and it "
            f"was {verdict}."
        )
    source = items[item.sample_id]
    return ErrorExample(
        kind=kind,
        sample_id=item.sample_id,
        benchmark=source.benchmark.value,
        task_group=item.group,
        prompt_excerpt=excerpt(source.question),
        chosen_model_id=item.chosen,
        chosen_correct=chosen.correct,
        chosen_cost_usd=chosen.cost_usd,
        chosen_latency_ms=chosen.latency_ms,
        predicted_success=round(p, 4),
        alternative_model_id=alternative,
        alternative_correct=None if other is None else other.correct,
        alternative_cost_usd=None if other is None else other.cost_usd,
        alternative_latency_ms=None if other is None else other.latency_ms,
        explanation=explanation,
    )


def _examples(
    verdicts: list[PromptVerdict],
    cells: dict[tuple[str, str], Cell],
    predicted: Callable[[str, str], float],
    items: dict[str, SuiteItem],
    names: dict[str, str],
    models: list[str],
) -> list[ErrorExample]:
    """The most telling cases: the most confident misses, the costliest over-routing, and the
    largest savings against always using the strongest model."""
    under = sorted(
        (item for item in verdicts if item.under),
        key=lambda item: (-predicted(item.sample_id, item.chosen), item.sample_id),
    )
    over = sorted(
        (item for item in verdicts if item.over),
        key=lambda item: (-item.extra_cost, item.sample_id),
    )
    good: list[PromptVerdict] = []
    if STRONGEST in models:
        good = sorted(
            (
                item for item in verdicts
                if item.correct and item.chosen != STRONGEST
            ),
            key=lambda item: (
                not cells[(item.sample_id, STRONGEST)].correct,  # prefer cases both got right
                -(cells[(item.sample_id, STRONGEST)].cost_usd
                  - cells[(item.sample_id, item.chosen)].cost_usd),
                item.sample_id,
            ),
        )
    examples = [
        _example("under", item, item.under, cells, predicted, items, names)
        for item in under[:EXAMPLES_PER_KIND]
    ]
    examples += [
        _example("over", item, item.over, cells, predicted, items, names)
        for item in over[:EXAMPLES_PER_KIND]
    ]
    examples += [
        _example("good", item, STRONGEST, cells, predicted, items, names)
        for item in good[:EXAMPLES_PER_KIND]
    ]
    return examples
