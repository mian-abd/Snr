from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import (
    ModelSpec,
    RoutingPool,
    RoutingPriority,
    RoutingValidationCase,
    RoutingValidationReport,
)
from app.routing.policy import (
    CHEAP_MODEL_ID,
    PAID_BUDGET_MODEL_ID,
    PAID_EFFICIENT_MODEL_ID,
    PAID_QUALITY_MODEL_ID,
    STRONG_MODEL_ID,
    RuleBasedRouter,
)


@dataclass(frozen=True)
class ReferenceCase:
    case_id: str
    label: str
    prompt: str
    priority: RoutingPriority
    min_context_tokens: int
    expected_model_id: str


GENERAL_PROMPT = "Explain the water cycle in two sentences."
SIMPLE_MATH_PROMPT = "Calculate 18 + 24."
COMPLEX_MATH_PROMPT = "Calculate 18 + 24 + 31 + 7 and explain the result."

BASELINE_CASES = (
    ReferenceCase(
        case_id="cost_general",
        label="Cost preference",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.COST,
        min_context_tokens=1,
        expected_model_id=CHEAP_MODEL_ID,
    ),
    ReferenceCase(
        case_id="latency_general",
        label="Latency preference",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.LATENCY,
        min_context_tokens=1,
        expected_model_id=CHEAP_MODEL_ID,
    ),
    ReferenceCase(
        case_id="quality_general",
        label="Quality preference",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.QUALITY,
        min_context_tokens=1,
        expected_model_id=STRONG_MODEL_ID,
    ),
    ReferenceCase(
        case_id="balanced_math",
        label="Balanced complex task",
        prompt=COMPLEX_MATH_PROMPT,
        priority=RoutingPriority.BALANCED,
        min_context_tokens=1,
        expected_model_id=STRONG_MODEL_ID,
    ),
    ReferenceCase(
        case_id="hard_requirement_override",
        label="Hard requirement override",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.COST,
        min_context_tokens=500_000,
        expected_model_id=STRONG_MODEL_ID,
    ),
)

PAID_CASES = (
    ReferenceCase(
        case_id="cost_general",
        label="Cost preference",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.COST,
        min_context_tokens=1,
        expected_model_id=PAID_BUDGET_MODEL_ID,
    ),
    ReferenceCase(
        case_id="latency_general",
        label="Latency preference",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.LATENCY,
        min_context_tokens=1,
        expected_model_id=PAID_EFFICIENT_MODEL_ID,
    ),
    ReferenceCase(
        case_id="quality_general",
        label="Quality preference",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.QUALITY,
        min_context_tokens=1,
        expected_model_id=PAID_QUALITY_MODEL_ID,
    ),
    ReferenceCase(
        case_id="balanced_general",
        label="Balanced general task",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.BALANCED,
        min_context_tokens=1,
        expected_model_id=PAID_BUDGET_MODEL_ID,
    ),
    ReferenceCase(
        case_id="balanced_simple_math",
        label="Balanced moderate task",
        prompt=SIMPLE_MATH_PROMPT,
        priority=RoutingPriority.BALANCED,
        min_context_tokens=1,
        expected_model_id=PAID_EFFICIENT_MODEL_ID,
    ),
    ReferenceCase(
        case_id="balanced_complex_math",
        label="Balanced complex task",
        prompt=COMPLEX_MATH_PROMPT + " Show every intermediate step and check the total twice "
        "before giving the final answer, because the explanation will be graded for "
        "completeness, accuracy, and clarity by a teacher who expects a careful, "
        "well-organized written solution.",
        priority=RoutingPriority.BALANCED,
        min_context_tokens=1,
        expected_model_id=PAID_QUALITY_MODEL_ID,
    ),
    ReferenceCase(
        case_id="hard_requirement_override",
        label="Hard requirement override",
        prompt=GENERAL_PROMPT,
        priority=RoutingPriority.COST,
        min_context_tokens=500_000,
        expected_model_id=PAID_EFFICIENT_MODEL_ID,
    ),
)

STRATEGY_IDS = {RoutingPool.BASELINE: "rule_based_v1", RoutingPool.PAID: "rule_based_paid_v1"}
REFERENCE_CASES = {RoutingPool.BASELINE: BASELINE_CASES, RoutingPool.PAID: PAID_CASES}


def build_validation_report(
    models: list[ModelSpec], pool: RoutingPool = RoutingPool.BASELINE
) -> RoutingValidationReport:
    """Evaluate deterministic CP2 reference cases without provider calls."""
    router = RuleBasedRouter()
    cases: list[RoutingValidationCase] = []
    for reference in REFERENCE_CASES[pool]:
        decision = router.decide(
            prompt=reference.prompt,
            priority=reference.priority,
            models=models,
            pool=pool,
            min_context_tokens=reference.min_context_tokens,
        )
        cases.append(
            RoutingValidationCase(
                case_id=reference.case_id,
                label=reference.label,
                prompt=reference.prompt,
                priority=reference.priority,
                min_context_tokens=reference.min_context_tokens,
                expected_model_id=reference.expected_model_id,
                decision=decision,
                passed=decision.selected_model_id == reference.expected_model_id,
            )
        )

    passed_cases = sum(case.passed for case in cases)
    return RoutingValidationReport(
        strategy_id=STRATEGY_IDS[pool],
        registry_snapshot_id=models[0].snapshot_id,
        passed=passed_cases == len(cases),
        passed_cases=passed_cases,
        total_cases=len(cases),
        cases=cases,
    )
