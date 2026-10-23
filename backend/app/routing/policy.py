from __future__ import annotations

import re

from app.domain.models import (
    EligibilityRequest,
    ModelSpec,
    RoutingDecision,
    RoutingPool,
    RoutingPriority,
)
from app.registry.filtering import evaluate_eligibility

CHEAP_MODEL_ID = "google/gemma-4-26b-a4b-it:free"
STRONG_MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b:free"
PAID_BUDGET_MODEL_ID = "google/gemma-4-26b-a4b-it"
PAID_EFFICIENT_MODEL_ID = "inception/mercury-3"
PAID_QUALITY_MODEL_ID = "google/gemini-4-argon"
HIGH_EFFORT_SIGNALS = frozenset({"math", "code", "long_prompt", "many_numbers"})
# Paid pool only: balanced routing escalates to the quality model at this many signals.
HIGH_EFFORT_THRESHOLD = 3


def effort_score(signals: list[str]) -> int:
    """Count visible higher-effort signals; the CP2 stand-in for a difficulty score."""
    return len(HIGH_EFFORT_SIGNALS.intersection(signals))


def prompt_signals(prompt: str) -> list[str]:
    """Return transparent, deliberately lightweight prompt features for CP2."""
    normalized = prompt.lower()
    signals: list[str] = []
    if re.search(
        r"\b(solve|calculate|ratio|percent|equation|number)\b|[=+*/]", normalized
    ):
        signals.append("math")
    if "```" in prompt or re.search(
        r"\b(function|class|debug|python|javascript|code)\b", normalized
    ):
        signals.append("code")
    if len(prompt.split()) >= 45:
        signals.append("long_prompt")
    if len(re.findall(r"\d+(?:\.\d+)?", prompt)) >= 4:
        signals.append("many_numbers")
    return signals or ["general"]


class RuleBasedRouter:
    """A small, inspectable CP2 policy. It is intentionally not learned."""

    def decide(
        self,
        *,
        prompt: str,
        priority: RoutingPriority,
        models: list[ModelSpec],
        pool: RoutingPool = RoutingPool.BASELINE,
        min_context_tokens: int = 1,
    ) -> RoutingDecision:
        eligibility = evaluate_eligibility(
            models, EligibilityRequest(min_context_tokens=min_context_tokens)
        )
        eligible_ids = [item.model_id for item in eligibility if item.eligible]
        if not eligible_ids:
            raise ValueError("No model satisfies the current hard requirements")

        signals = prompt_signals(prompt)
        if pool == RoutingPool.PAID:
            cheap_id = PAID_BUDGET_MODEL_ID
            latency_id = PAID_EFFICIENT_MODEL_ID
            strong_id = PAID_QUALITY_MODEL_ID
        else:
            cheap_id = CHEAP_MODEL_ID
            latency_id = CHEAP_MODEL_ID
            strong_id = STRONG_MODEL_ID
        cheap_available = cheap_id in eligible_ids
        latency_available = latency_id in eligible_ids
        strong_available = strong_id in eligible_ids
        cheap = cheap_id if cheap_available else eligible_ids[0]
        latency = latency_id if latency_available else eligible_ids[0]
        strong = strong_id if strong_available else eligible_ids[-1]

        if priority == RoutingPriority.COST:
            selected = cheap
            reason = (
                "Cost priority selects the designated cheaper/smaller baseline."
                if cheap_available
                else "Cost priority would prefer the cheaper/smaller baseline, but it was "
                "filtered out by hard requirements; the remaining eligible model is selected."
            )
        elif priority == RoutingPriority.QUALITY:
            selected = strong
            reason = (
                "Quality priority selects the designated stronger baseline."
                if strong_available
                else "Quality priority would prefer the stronger baseline, but it was filtered "
                "out by hard requirements; the remaining eligible model is selected."
            )
        elif priority == RoutingPriority.LATENCY:
            selected = latency
            reason = (
                "Latency priority selects the designated low-latency candidate."
                if latency_available
                else "Latency priority would prefer the designated low-latency candidate, but "
                "it was filtered out by hard requirements; the remaining eligible model is "
                "selected."
            )
        elif pool == RoutingPool.PAID and 0 < effort_score(signals) < HIGH_EFFORT_THRESHOLD:
            selected = latency
            reason = (
                f"Balanced priority found {effort_score(signals)} higher-effort signal(s), "
                f"below the {HIGH_EFFORT_THRESHOLD}-signal threshold for the quality model, "
                "and selects the mid-tier efficient candidate."
                if latency_available
                else "Balanced priority would prefer the mid-tier efficient candidate, but it "
                "was filtered out by hard requirements; the remaining eligible model is "
                "selected."
            )
        elif effort_score(signals):
            selected = strong
            reason = (
                "Balanced priority detected a higher-effort task signal and selects the "
                "stronger baseline."
                if strong_available
                else "Balanced priority detected a higher-effort task signal, but the stronger "
                "baseline was filtered out; the remaining eligible model is selected."
            )
        else:
            selected = cheap
            reason = (
                "Balanced priority found no higher-effort signal and selects the "
                "cheaper/smaller baseline."
                if cheap_available
                else "Balanced priority found no higher-effort signal, but the cheaper/smaller "
                "baseline was filtered out; the remaining eligible model is selected."
            )

        return RoutingDecision(
            strategy_id="rule_based_v1" if pool == RoutingPool.BASELINE else "rule_based_paid_v1",
            pool=pool,
            priority=priority,
            min_context_tokens=min_context_tokens,
            selected_model_id=selected,
            eligible_model_ids=eligible_ids,
            task_signals=signals,
            reason=reason,
        )
