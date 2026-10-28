"""Multi-objective scoring over eligible models (proposal, "Routing Strategies").

score = quality_weight * P(success)
        - cost_weight * normalized expected cost
        - latency_weight * normalized expected latency
        - reliability_weight * observed failure rate

Hard requirements are applied before this module is called; only eligible candidates are scored.
Cost and latency are divided by the largest eligible value, which keeps ratios between models
(an expensive model stays many times costlier) while mapping every candidate into [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import RoutingPriority


@dataclass(frozen=True)
class PolicyWeights:
    quality: float
    cost: float
    latency: float
    reliability: float = 0.0


# One preset per user priority. The emphasised objective gets 0.5, not 1.0: the costliest model
# always scores a full normalized 1.0 penalty, so a weight of 1.0 would let a model expected to
# fail win just for being cheap. At 0.5 a cheap model wins only when its quality is close.
# These are starting presets; the proposal tunes user weights on validation data (week of Nov 5).
POLICY_WEIGHTS: dict[RoutingPriority, PolicyWeights] = {
    RoutingPriority.QUALITY: PolicyWeights(quality=1.0, cost=0.02, latency=0.02, reliability=0.5),
    RoutingPriority.COST: PolicyWeights(quality=1.0, cost=0.5, latency=0.05, reliability=0.5),
    RoutingPriority.LATENCY: PolicyWeights(quality=1.0, cost=0.05, latency=0.5, reliability=0.5),
    RoutingPriority.BALANCED: PolicyWeights(quality=1.0, cost=0.2, latency=0.2, reliability=0.5),
}


@dataclass(frozen=True)
class CandidateEstimate:
    model_id: str
    p_success: float
    expected_cost_usd: float
    expected_latency_ms: float
    failure_rate: float = 0.0


@dataclass(frozen=True)
class ScoredCandidate:
    model_id: str
    score: float
    p_success: float
    normalized_cost: float
    normalized_latency: float
    failure_rate: float


def _scale_to_max(values: list[float]) -> list[float]:
    largest = max(values)
    if largest <= 0:
        return [0.0 for _ in values]
    return [max(value, 0.0) / largest for value in values]


def score_candidates(
    candidates: list[CandidateEstimate], weights: PolicyWeights
) -> list[ScoredCandidate]:
    """Score eligible candidates, best first. Ties go to the cheaper model, then the model ID."""
    if not candidates:
        raise ValueError("No eligible candidates to score")
    for candidate in candidates:
        if not 0.0 <= candidate.p_success <= 1.0:
            raise ValueError(f"p_success out of range for {candidate.model_id}")
    costs = _scale_to_max([item.expected_cost_usd for item in candidates])
    latencies = _scale_to_max([item.expected_latency_ms for item in candidates])
    scored = [
        ScoredCandidate(
            model_id=item.model_id,
            score=(
                weights.quality * item.p_success
                - weights.cost * cost
                - weights.latency * latency
                - weights.reliability * item.failure_rate
            ),
            p_success=item.p_success,
            normalized_cost=cost,
            normalized_latency=latency,
            failure_rate=item.failure_rate,
        )
        for item, cost, latency in zip(candidates, costs, latencies, strict=True)
    ]
    return sorted(scored, key=lambda item: (-item.score, item.normalized_cost, item.model_id))


def choose(candidates: list[CandidateEstimate], priority: RoutingPriority) -> ScoredCandidate:
    return score_candidates(candidates, POLICY_WEIGHTS[priority])[0]
