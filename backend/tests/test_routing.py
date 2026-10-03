from app.domain.models import RoutingPriority
from app.routing.policy import CHEAP_MODEL_ID, STRONG_MODEL_ID, RuleBasedRouter
from app.routing.replay import build_dashboard


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
