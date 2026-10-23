from app.domain.models import RoutingPool, RoutingPriority
from app.routing.policy import (
    CHEAP_MODEL_ID,
    PAID_BUDGET_MODEL_ID,
    PAID_EFFICIENT_MODEL_ID,
    PAID_QUALITY_MODEL_ID,
    STRONG_MODEL_ID,
    RuleBasedRouter,
    effort_score,
)
from app.routing.replay import build_dashboard
from app.routing.validation import build_validation_report


def test_rule_router_changes_selection_for_priority_and_signals(registry) -> None:
    router = RuleBasedRouter()
    cost = router.decide(
        prompt="Explain the water cycle.",
        priority=RoutingPriority.COST,
        models=registry.models,
    )
    quality = router.decide(
        prompt="Explain the water cycle.",
        priority=RoutingPriority.QUALITY,
        models=registry.models,
    )
    balanced_math = router.decide(
        prompt="Calculate 18 + 24 + 31 + 7.",
        priority=RoutingPriority.BALANCED,
        models=registry.models,
    )
    assert cost.selected_model_id == CHEAP_MODEL_ID
    assert quality.selected_model_id == STRONG_MODEL_ID
    assert balanced_math.selected_model_id == STRONG_MODEL_ID
    assert "math" in balanced_math.task_signals


def test_rule_router_respects_context_requirement(registry) -> None:
    decision = RuleBasedRouter().decide(
        prompt="Explain this document.",
        priority=RoutingPriority.COST,
        models=registry.models,
        min_context_tokens=500_000,
    )
    assert decision.selected_model_id == STRONG_MODEL_ID
    assert decision.eligible_model_ids == [STRONG_MODEL_ID]
    assert "filtered out by hard requirements" in decision.reason


def test_paid_pool_uses_three_distinct_roles(paid_registry) -> None:
    router = RuleBasedRouter()
    cost = router.decide(
        prompt="Explain the water cycle.",
        priority=RoutingPriority.COST,
        pool=RoutingPool.PAID,
        models=paid_registry.models,
    )
    latency = router.decide(
        prompt="Explain the water cycle.",
        priority=RoutingPriority.LATENCY,
        pool=RoutingPool.PAID,
        models=paid_registry.models,
    )
    quality = router.decide(
        prompt="Explain the water cycle.",
        priority=RoutingPriority.QUALITY,
        pool=RoutingPool.PAID,
        models=paid_registry.models,
    )
    assert cost.selected_model_id == PAID_BUDGET_MODEL_ID
    assert latency.selected_model_id == PAID_EFFICIENT_MODEL_ID
    assert quality.selected_model_id == PAID_QUALITY_MODEL_ID


def test_dashboard_replays_checkpoint_one_matrix_without_live_calls() -> None:
    from app.config import REPOSITORY_ROOT

    dashboard = build_dashboard(REPOSITORY_ROOT / "data" / "demo" / "checkpoint-1")
    summaries = {item.strategy_id: item for item in dashboard.strategies}
    assert dashboard.source_cells == 24
    assert summaries["fixed_cheap"].attempted == 12
    assert summaries["fixed_cheap"].successful == 3
    assert summaries["fixed_cheap"].correct == 3
    assert summaries["fixed_strong"].attempted == 12
    assert summaries["fixed_strong"].successful == 12
    assert summaries["fixed_strong"].correct == 8
    assert summaries["fixed_strong"].median_latency_ms is not None
    assert summaries["fixed_strong"].p95_latency_ms is not None
    assert len(dashboard.prompts) == 12
    first = dashboard.prompts[0]
    assert {cell.model_id for cell in first.cells} == {CHEAP_MODEL_ID, STRONG_MODEL_ID}
    assert [selection.strategy_id for selection in first.selections] == [
        summary.strategy_id for summary in dashboard.strategies
    ]
    assert all(selection.reason for selection in first.selections)


def test_paid_balanced_policy_uses_three_tiers(paid_registry) -> None:
    router = RuleBasedRouter()

    def balanced(prompt: str) -> str:
        return router.decide(
            prompt=prompt,
            priority=RoutingPriority.BALANCED,
            pool=RoutingPool.PAID,
            models=paid_registry.models,
        ).selected_model_id

    assert effort_score(["general"]) == 0
    assert effort_score(["math", "long_prompt", "many_numbers"]) == 3
    assert balanced("Explain the water cycle.") == PAID_BUDGET_MODEL_ID
    assert balanced("Calculate 18 + 24.") == PAID_EFFICIENT_MODEL_ID
    assert balanced("Calculate 1 + 2 + 3 + 4. " + "Show each step clearly. " * 10) == (
        PAID_QUALITY_MODEL_ID
    )


def test_paid_validation_report_passes_all_reference_cases(paid_registry) -> None:
    report = build_validation_report(paid_registry.models, pool=RoutingPool.PAID)
    cases = {case.case_id: case for case in report.cases}

    assert report.strategy_id == "rule_based_paid_v1"
    assert report.passed is True
    assert report.passed_cases == report.total_cases == 7
    override = cases["hard_requirement_override"].decision
    assert PAID_BUDGET_MODEL_ID not in override.eligible_model_ids
    assert override.selected_model_id == PAID_EFFICIENT_MODEL_ID


def test_paid_dashboard_replays_saved_paid_matrix() -> None:
    from app.config import REPOSITORY_ROOT

    dashboard = build_dashboard(
        REPOSITORY_ROOT / "data" / "demo" / "checkpoint-2-paid", pool=RoutingPool.PAID
    )
    summaries = {item.strategy_id: item for item in dashboard.strategies}
    assert dashboard.pool == RoutingPool.PAID
    assert dashboard.source_cells == 36
    assert len(dashboard.model_ids) == 3
    assert summaries["fixed_cheap"].selected_model_counts == {PAID_BUDGET_MODEL_ID: 12}
    assert summaries["fixed_strong"].selected_model_counts == {PAID_QUALITY_MODEL_ID: 12}
    assert summaries["rule_latency"].selected_model_counts == {PAID_EFFICIENT_MODEL_ID: 12}
    balanced = summaries["rule_balanced"].selected_model_counts
    assert set(balanced) == {PAID_EFFICIENT_MODEL_ID, PAID_QUALITY_MODEL_ID}
    assert sum(balanced.values()) == 12
    assert summaries["fixed_strong"].total_cost_usd is not None
    assert summaries["fixed_strong"].total_cost_usd > 0


def test_validation_report_proves_priorities_and_hard_requirement(registry) -> None:
    report = build_validation_report(registry.models)
    cases = {case.case_id: case for case in report.cases}

    assert report.strategy_id == "rule_based_v1"
    assert report.total_cases == 5
    assert report.passed_cases == 5
    assert report.passed is True
    assert cases["cost_general"].decision.selected_model_id == CHEAP_MODEL_ID
    assert cases["latency_general"].decision.selected_model_id == CHEAP_MODEL_ID
    assert cases["quality_general"].decision.selected_model_id == STRONG_MODEL_ID
    assert cases["balanced_math"].decision.selected_model_id == STRONG_MODEL_ID
    assert cases["hard_requirement_override"].decision.eligible_model_ids == [
        STRONG_MODEL_ID
    ]
