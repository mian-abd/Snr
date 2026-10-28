import pytest

from app.domain.models import RoutingPriority
from app.routing.multi_objective import (
    POLICY_WEIGHTS,
    CandidateEstimate,
    PolicyWeights,
    choose,
    score_candidates,
)

CHEAP = CandidateEstimate("cheap", p_success=0.80, expected_cost_usd=0.0001, expected_latency_ms=3000)  # noqa: E501
FAST = CandidateEstimate("fast", p_success=0.75, expected_cost_usd=0.0001, expected_latency_ms=600)
STRONG = CandidateEstimate("strong", p_success=0.97, expected_cost_usd=0.003, expected_latency_ms=5000)  # noqa: E501


def test_priorities_pick_different_models_for_the_same_estimates() -> None:
    pool = [CHEAP, FAST, STRONG]
    assert choose(pool, RoutingPriority.QUALITY).model_id == "strong"
    assert choose(pool, RoutingPriority.COST).model_id == "cheap"
    assert choose(pool, RoutingPriority.LATENCY).model_id == "fast"


def test_score_matches_the_proposal_formula() -> None:
    weights = PolicyWeights(quality=1.0, cost=0.5, latency=0.25, reliability=2.0)
    unreliable = CandidateEstimate("x", 0.9, 0.002, 1000, failure_rate=0.1)
    best = CandidateEstimate("y", 0.6, 0.004, 4000)
    scored = {item.model_id: item for item in score_candidates([unreliable, best], weights)}
    # Normalized by the largest eligible value: x has half the cost and a quarter of the latency.
    assert scored["x"].normalized_cost == pytest.approx(0.5)
    assert scored["x"].normalized_latency == pytest.approx(0.25)
    assert scored["x"].score == pytest.approx(0.9 - 0.5 * 0.5 - 0.25 * 0.25 - 2.0 * 0.1)
    assert scored["y"].score == pytest.approx(0.6 - 0.5 * 1.0 - 0.25 * 1.0)


def test_quality_still_matters_under_cost_priority() -> None:
    hopeless = CandidateEstimate("hopeless", 0.05, 0.00001, 500)
    good = CandidateEstimate("good", 0.95, 0.0003, 900)
    assert choose([hopeless, good], RoutingPriority.COST).model_id == "good"


def test_ties_prefer_the_cheaper_model_and_free_models_score_zero_cost() -> None:
    free = CandidateEstimate("free", 0.9, 0.0, 1000)
    paid = CandidateEstimate("paid", 0.9, 0.0, 1000)
    ranked = score_candidates([paid, free], PolicyWeights(1.0, 1.0, 1.0))
    assert ranked[0].normalized_cost == 0.0
    assert [item.model_id for item in ranked] == ["free", "paid"]


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        score_candidates([], POLICY_WEIGHTS[RoutingPriority.BALANCED])
    with pytest.raises(ValueError):
        score_candidates([CandidateEstimate("bad", 1.5, 0.0, 1.0)], PolicyWeights(1, 1, 1))
