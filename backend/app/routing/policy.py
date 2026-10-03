from __future__ import annotations

import re

from app.domain.models import (
    EligibilityRequest,
    ModelSpec,
    RoutingDecision,
    RoutingPriority,
)
from app.registry.filtering import evaluate_eligibility

CHEAP_MODEL_ID = "google/gemma-4-26b-a4b-it:free"
STRONG_MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b:free"


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
        min_context_tokens: int = 1,
    ) -> RoutingDecision:
        eligibility = evaluate_eligibility(
            models, EligibilityRequest(min_context_tokens=min_context_tokens)
        )
        eligible_ids = [item.model_id for item in eligibility if item.eligible]
        if not eligible_ids:
            raise ValueError("No model satisfies the current hard requirements")

        signals = prompt_signals(prompt)
        cheap = CHEAP_MODEL_ID if CHEAP_MODEL_ID in eligible_ids else eligible_ids[0]
        strong = STRONG_MODEL_ID if STRONG_MODEL_ID in eligible_ids else eligible_ids[-1]

        if priority == RoutingPriority.COST:
            selected, reason = (
                cheap,
                "Cost priority selects the designated cheaper/smaller baseline.",
            )
        elif priority == RoutingPriority.QUALITY:
            selected, reason = strong, "Quality priority selects the designated stronger baseline."
        elif priority == RoutingPriority.LATENCY:
            selected, reason = (
                cheap,
                "Latency priority selects the smaller baseline for a faster first attempt.",
            )
        elif {"math", "code", "long_prompt", "many_numbers"}.intersection(signals):
            selected, reason = (
                strong,
                "Balanced priority detected a higher-effort task signal and selects the "
                "stronger baseline.",
            )
        else:
            selected, reason = (
                cheap,
                "Balanced priority found no higher-effort signal and selects the "
                "cheaper/smaller baseline.",
            )

        return RoutingDecision(
            strategy_id="rule_based_v1",
            priority=priority,
            selected_model_id=selected,
            eligible_model_ids=eligible_ids,
            task_signals=signals,
            reason=reason,
        )
