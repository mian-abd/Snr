"""Robustness tests: replay stored results while routing conditions change (week of Nov 19).

Proposal: "robustness tests that replay stored results while changing model price, latency,
reliability, or user priorities." Nothing here calls a provider. A scenario changes two things:

- the world: what a call would now cost, how long it would take, or whether it fails. Stored
  cells are rescaled; injected failures are chosen by a fixed hash of (model, prompt), so a
  larger failure share always contains a smaller one.
- what the router knows. The adapted router is told about the change, as the live catalog
  (price, availability) or call monitoring (latency, failure rate) would tell it. The frozen
  router keeps its trained estimates. Neither is retrained, and the classifier never changes.

Baselines follow the world but never adapt. When their pinned model is gone they fall back the
way the Checkpoint 2 rule router does (the first eligible model in its registry order). The
oracle sees the changed world with perfect hindsight.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from statistics import median

from app.benchmarks.suite import SuiteItem
from app.domain.models import (
    LiveCatalogStatus,
    PrioritySweepPoint,
    RobustnessReport,
    RoutingPriority,
    RoutingWeights,
    ScenarioResult,
    ScenarioSpec,
    ScenarioStrategy,
)
from app.learned.evaluate import CHEAPEST, FASTEST, STRONGEST
from app.learned.features import Cell
from app.learned.router import LearnedRouter, policy_weights
from app.routing.multi_objective import CandidateEstimate, score_candidates
from app.routing.policy import effort_score, prompt_signals

INJECTED_FAILURE_LATENCY_MS = 2000.0  # an outage modelled as an error returned after 2 s
RETIRED_LATENCY_MS = 400.0  # used only when no real retired-model call was recorded


def retired_call_latency(cells: Iterable[Cell], model_id: str = FASTEST) -> float:
    """The median latency of a model's failed calls after it was retired (its real 404s)."""
    failed = [cell.latency_ms for cell in cells if cell.model_id == model_id and not cell.served]
    return median(failed) if failed else RETIRED_LATENCY_MS
CP2_REGISTRY_ORDER = (CHEAPEST, FASTEST, STRONGEST)  # rule-router fallback order
SWEEP_WEIGHTS = (0.0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0)
RELIABILITY_ON = 1.0  # one failure costs as much as one certain success


@dataclass(frozen=True)
class Knowledge:
    """What the router is told on top of its trained estimates."""

    unavailable: frozenset[str] = frozenset()
    price: dict[str, float] = field(default_factory=dict)
    latency: dict[str, float] = field(default_factory=dict)
    failure: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_scenario(cls, spec: ScenarioSpec) -> Knowledge:
        return cls(
            unavailable=frozenset(spec.unavailable),
            price=dict(spec.price_multipliers),
            latency=dict(spec.latency_multipliers),
            failure=dict(spec.failure_shares),
        )

    def plus(self, other: Knowledge) -> Knowledge:
        """Both changes at once: multipliers multiply and failure shares compound."""
        return Knowledge(
            unavailable=self.unavailable | other.unavailable,
            price=_combine(self.price, other.price, lambda a, b: a * b, 1.0),
            latency=_combine(self.latency, other.latency, lambda a, b: a * b, 1.0),
            failure=_combine(self.failure, other.failure, lambda a, b: 1 - (1 - a) * (1 - b), 0.0),
        )

    def minus(self, other: Knowledge) -> Knowledge:
        """Undo a change this knowledge already contains: multipliers divide out."""
        return Knowledge(
            unavailable=self.unavailable - other.unavailable,
            price=_drop_unit({k: v / other.price.get(k, 1.0) for k, v in self.price.items()}),
            latency=_drop_unit(
                {k: v / other.latency.get(k, 1.0) for k, v in self.latency.items()}
            ),
            failure={k: v for k, v in self.failure.items() if k not in other.failure},
        )


def _combine(
    first: dict[str, float],
    second: dict[str, float],
    merge: Callable[[float, float], float],
    neutral: float,
) -> dict[str, float]:
    merged = dict(first)
    for key, value in second.items():
        merged[key] = merge(merged.get(key, neutral), value)
    return merged


def _drop_unit(values: dict[str, float]) -> dict[str, float]:
    return {key: value for key, value in values.items() if abs(value - 1.0) > 1e-12}


def catalog_knowledge(catalog: LiveCatalogStatus | None) -> Knowledge:
    """Turn a saved live-catalog check into scalar knowledge (unavailable models, price ratios).

    The live router scales cost by the price ratio at each prompt's token mix. Every repricing
    observed so far moved input and output prices by the same ratio, where the scalar is exact.
    """
    if catalog is None:
        return Knowledge()
    unavailable = frozenset(item.model_id for item in catalog.models if not item.available)
    price: dict[str, float] = {}
    for item in catalog.models:
        if item.live_prompt_price_per_million is None:
            continue
        ratios = [
            live / snapshot
            for live, snapshot in (
                (item.live_prompt_price_per_million, item.snapshot_prompt_price_per_million),
                (
                    item.live_completion_price_per_million,
                    item.snapshot_completion_price_per_million,
                ),
            )
            if live is not None and snapshot > 0
        ]
        if not ratios and (
            item.live_prompt_price_per_million or item.live_completion_price_per_million
        ):
            raise ValueError(f"{item.model_id}: a free model started charging; replay cannot scale")
        if ratios and abs(ratios[0] - 1.0) > 1e-12:
            if max(ratios) - min(ratios) > 1e-9:
                raise ValueError(f"{item.model_id}: input and output prices moved differently")
            price[item.model_id] = ratios[0]
    return Knowledge(unavailable=unavailable, price=price)


class RouterView:
    """The exported router with every P(success) precomputed, so what-ifs replay quickly.

    ``choose`` scores candidates exactly as ``LearnedRouter.decide_for`` does; a test checks
    that the two agree on every prompt.
    """

    def __init__(self, router: LearnedRouter, items: dict[str, SuiteItem], prompts: list[str]):
        self.router = router
        self.items = items
        self.p = {
            (sample, model_id): router.p_success(
                items[sample].question, items[sample].task_group, len(items[sample].options),
                router.models[model_id],
            )
            for sample in prompts
            for model_id in router.pool_ids
        }

    def choose(self, sample: str, weights: RoutingWeights, knowledge: Knowledge) -> str:
        group = self.items[sample].task_group
        candidates = []
        for model_id in self.router.pool_ids:
            if model_id in knowledge.unavailable:
                continue
            estimate = self.router.artifact.estimates[model_id][group]
            injected = knowledge.failure.get(model_id, 0.0)
            candidates.append(
                CandidateEstimate(
                    model_id=model_id,
                    p_success=self.p[(sample, model_id)],
                    expected_cost_usd=estimate.expected_cost_usd
                    * knowledge.price.get(model_id, 1.0),
                    expected_latency_ms=estimate.expected_latency_ms
                    * knowledge.latency.get(model_id, 1.0),
                    failure_rate=1 - (1 - estimate.failure_rate) * (1 - injected),
                )
            )
        return score_candidates(candidates, policy_weights(weights))[0].model_id


def _unit_hash(model_id: str, sample_id: str) -> float:
    digest = hashlib.sha256(f"robustness-v1|{model_id}|{sample_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class World:
    """Stored outcomes, optionally changed by a scenario."""

    def __init__(self, cells: Iterable[Cell], retired_latency_ms: float = RETIRED_LATENCY_MS):
        self.cells = {(cell.sample_id, cell.model_id): cell for cell in cells}
        # How long a call to a retired model takes to fail: pass the measured 404 latency.
        self.retired_latency_ms = retired_latency_ms

    def outcome(
        self, sample: str, model_id: str, spec: ScenarioSpec | None = None
    ) -> tuple[bool, float, float, bool]:
        cell = self.cells[(sample, model_id)]
        if spec is None or spec.world_already_changed:
            return cell.correct, cell.cost_usd, cell.latency_ms, cell.served
        if model_id in spec.unavailable:
            if not cell.served:
                return False, cell.cost_usd, cell.latency_ms, False
            return False, 0.0, self.retired_latency_ms, False
        if _unit_hash(model_id, sample) < spec.failure_shares.get(model_id, 0.0):
            return False, 0.0, INJECTED_FAILURE_LATENCY_MS, False
        return (
            cell.correct,
            cell.cost_usd * spec.price_multipliers.get(model_id, 1.0),
            cell.latency_ms * spec.latency_multipliers.get(model_id, 1.0),
            cell.served,
        )


def _rule_choice(item: SuiteItem, unavailable: frozenset[str]) -> str:
    score = effort_score(prompt_signals(item.question))
    wanted = STRONGEST if score >= 3 else FASTEST if score else CHEAPEST
    if wanted not in unavailable:
        return wanted
    return next(model for model in CP2_REGISTRY_ORDER if model not in unavailable)


def _fixed(model_id: str) -> Callable[[SuiteItem, frozenset[str]], str]:
    def choose(_: SuiteItem, unavailable: frozenset[str]) -> str:
        if model_id not in unavailable:
            return model_id
        return next(model for model in CP2_REGISTRY_ORDER if model not in unavailable)

    return choose


BASELINES: dict[str, Callable[[SuiteItem, frozenset[str]], str]] = {
    "fixed_cheapest": _fixed(CHEAPEST),
    "fixed_strongest": _fixed(STRONGEST),
    "rule_balanced": _rule_choice,
}


def _oracle_choice(
    world: World, sample: str, models: list[str], weights: RoutingWeights,
    spec: ScenarioSpec | None, unavailable: frozenset[str],
) -> str:
    candidates = []
    for model_id in sorted(models):
        if model_id in unavailable:
            continue
        correct, cost, latency, served = world.outcome(sample, model_id, spec)
        candidates.append(CandidateEstimate(
            model_id=model_id, p_success=float(correct), expected_cost_usd=cost,
            expected_latency_ms=latency, failure_rate=0.0 if served else 1.0,
        ))
    return score_candidates(candidates, policy_weights(weights))[0].model_id


def _summarize(
    strategy_id: str,
    picks: dict[str, str],
    world: World,
    spec: ScenarioSpec | None,
    reference: dict[str, str] | None,
) -> ScenarioStrategy:
    outcomes = [world.outcome(sample, model, spec) for sample, model in picks.items()]
    correct = sum(1 for ok, _, _, _ in outcomes if ok)
    return ScenarioStrategy(
        strategy_id=strategy_id,
        correct=correct,
        accuracy=correct / len(outcomes),
        total_cost_usd=round(sum(cost for _, cost, _, _ in outcomes), 6),
        median_latency_ms=round(median(latency for _, _, latency, _ in outcomes), 1),
        changed_decisions=(
            None if reference is None
            else sum(1 for sample, model in picks.items() if reference[sample] != model)
        ),
        selected_models=dict(Counter(picks.values()).most_common()),
    )


def _weights(base: RoutingWeights, spec: ScenarioSpec | None) -> RoutingWeights:
    if spec is None or spec.reliability_weight is None:
        return base
    return base.model_copy(update={"reliability": spec.reliability_weight})


def run_scenarios(
    evaluation_id: str,
    view: RouterView,
    world: World,
    prompts: list[str],
    models: list[str],
    scenarios: list[ScenarioSpec],
    base: Knowledge,
    notes: list[str],
) -> RobustnessReport:
    presets = view.router.artifact.weights
    reference = {
        priority: {sample: view.choose(sample, presets[priority], base) for sample in prompts}
        for priority in RoutingPriority
    }
    baseline_reference = {
        name: {sample: choose(view.items[sample], base.unavailable) for sample in prompts}
        for name, choose in BASELINES.items()
    }
    results = []
    for spec in scenarios:
        change = Knowledge.from_scenario(spec)
        if spec.world_already_changed:
            # The base knowledge already holds this observed change; frozen undoes it.
            adapted, frozen = base, base.minus(change)
        else:
            adapted, frozen = base.plus(change), base
        strategies: list[ScenarioStrategy] = []
        for name, choose_baseline in BASELINES.items():
            # Baselines never adapt, but a pinned model that is gone cannot be called.
            gone = frozenset(spec.unavailable) | base.unavailable
            picks = {sample: choose_baseline(view.items[sample], gone) for sample in prompts}
            strategies.append(
                _summarize(name, picks, world, spec, baseline_reference[name])
            )
        for priority in RoutingPriority:
            weights = _weights(presets[priority], spec)
            label = priority.value
            adapted_picks = {sample: view.choose(sample, weights, adapted) for sample in prompts}
            # The user's weights apply to both; only what the router knows differs.
            frozen_picks = {sample: view.choose(sample, weights, frozen) for sample in prompts}
            oracle_picks = {
                sample: _oracle_choice(world, sample, models, weights, spec, adapted.unavailable)
                for sample in prompts
            }
            strategies += [
                _summarize(f"learned:{label}", adapted_picks, world, spec, reference[priority]),
                _summarize(
                    f"learned_frozen:{label}", frozen_picks, world, spec, reference[priority]
                ),
                _summarize(f"oracle:{label}", oracle_picks, world, spec, None),
            ]
        results.append(ScenarioResult(scenario=spec, prompts=len(prompts), strategies=strategies))
    return RobustnessReport(
        evaluation_id=evaluation_id,
        prompts=len(prompts),
        scenarios=results,
        priority_sweep=priority_sweep(view, world, prompts, base),
        notes=notes,
    )


def priority_sweep(
    view: RouterView, world: World, prompts: list[str], base: Knowledge
) -> list[PrioritySweepPoint]:
    """Quality weight 1, one other weight varied, everything else 0 (user-priority robustness)."""
    points = []
    for axis in ("cost", "latency"):
        for weight in SWEEP_WEIGHTS:
            weights = RoutingWeights(
                cost=weight if axis == "cost" else 0.0,
                latency=weight if axis == "latency" else 0.0,
                reliability=0.0,
            )
            picks = {sample: view.choose(sample, weights, base) for sample in prompts}
            summary = _summarize("sweep", picks, world, None, None)
            points.append(PrioritySweepPoint(
                axis=axis, weight=weight, correct=summary.correct, accuracy=summary.accuracy,
                total_cost_usd=summary.total_cost_usd,
                median_latency_ms=summary.median_latency_ms,
                selected_models=summary.selected_models,
            ))
    return points


def standard_scenarios(
    models: list[str], *, gemma_price_ratio: float, drift_in_world: bool
) -> list[ScenarioSpec]:
    """The scenario set used for both evaluations; observed ones come first.

    ``drift_in_world`` is true for the final set, whose stored calls were made after the
    changes: Mercury's calls really failed and Gemma was really billed at the new price.
    """
    free_remote = [
        model for model in models
        if model in {"gpt-oss-120b", "llama-3.3-70b", "qwen-3.8-27b", "nemotron-3-ultra-free"}
    ]
    ovh = [model for model in models if model in {"gpt-oss-120b", "llama-3.3-70b", "qwen-3.8-27b"}]
    return [
        ScenarioSpec(
            scenario_id="observed_drift",
            title="Observed drift (Nov 12-13)",
            condition="availability",
            observed=True,
            description="OpenRouter stopped serving Mercury 3 and cut Gemma 4 26B's price by "
            f"{(1 - gemma_price_ratio):.0%}. The router that is told learns both from the live "
            "catalog; with its old estimates it still sends prompts to Mercury, and those calls "
            "fail.",
            unavailable=[FASTEST],
            price_multipliers={CHEAPEST: gemma_price_ratio},
            world_already_changed=drift_in_world,
        ),
        ScenarioSpec(
            scenario_id="gemma_price_x30",
            title="Gemma 4 26B costs 30x more",
            condition="price",
            observed=False,
            description="The cheap paid model becomes about as expensive as Gemini 4 Argon.",
            price_multipliers={CHEAPEST: 30.0},
        ),
        ScenarioSpec(
            scenario_id="gemini_price_x4",
            title="Gemini 4 Argon costs 4x more",
            condition="price",
            observed=False,
            description="The most expensive model gets dearer. Costs are scored relative to the "
            "most expensive model, so this tests whether the router still reacts.",
            price_multipliers={STRONGEST: 4.0},
        ),
        ScenarioSpec(
            scenario_id="gemini_price_div4",
            title="Gemini 4 Argon costs a quarter",
            condition="price",
            observed=False,
            description="The strongest model gets much cheaper.",
            price_multipliers={STRONGEST: 0.25},
        ),
        ScenarioSpec(
            scenario_id="ovh_latency_x3",
            title="Free OVHcloud endpoints 3x slower",
            condition="latency",
            observed=False,
            description="gpt-oss-120b, Llama 3.3 70B and Qwen 3.8 27B answer three times slower.",
            latency_multipliers={model: 3.0 for model in ovh},
        ),
        ScenarioSpec(
            scenario_id="gemma_latency_x3",
            title="Gemma 4 26B 3x slower",
            condition="latency",
            observed=False,
            description="The cheap paid model's host slows down threefold.",
            latency_multipliers={CHEAPEST: 3.0},
        ),
        ScenarioSpec(
            scenario_id="free_outage_50",
            title="Free endpoints fail half the time",
            condition="reliability",
            observed=False,
            description="Half of all calls to the four free remote models fail after 2 s. The "
            "tuned settings give reliability no weight, so the router knows the new failure rate "
            "but does not avoid the failing models.",
            failure_shares={model: 0.5 for model in free_remote},
        ),
        ScenarioSpec(
            scenario_id="free_outage_50_reliability",
            title="Same outage, reliability weighted",
            condition="reliability",
            observed=False,
            description="The same outage with the user's reliability weight raised from 0 to "
            f"{RELIABILITY_ON:g}, so a known failure rate counts against a model.",
            failure_shares={model: 0.5 for model in free_remote},
            reliability_weight=RELIABILITY_ON,
        ),
        ScenarioSpec(
            scenario_id="gemini_outage_30",
            title="Gemini 4 Argon fails 30% of calls",
            condition="reliability",
            observed=False,
            description="A partial outage of the strongest model, with reliability weighted "
            f"at {RELIABILITY_ON:g}.",
            failure_shares={STRONGEST: 0.3},
            reliability_weight=RELIABILITY_ON,
        ),
    ]
