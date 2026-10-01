from app.domain.models import EligibilityRequest, EligibilityResult, ModelSpec


def evaluate_eligibility(
    models: list[ModelSpec], requirements: EligibilityRequest
) -> list[EligibilityResult]:
    results: list[EligibilityResult] = []
    for model in models:
        reasons: list[str] = []
        if not model.enabled:
            reasons.append("model is disabled")
        if model.context_length < requirements.min_context_tokens:
            reasons.append(
                f"context length {model.context_length} < required "
                f"{requirements.min_context_tokens}"
            )
        results.append(
            EligibilityResult(
                model_id=model.id,
                eligible=not reasons,
                reasons=reasons or ["all requirements satisfied"],
                evaluated_requirements=requirements,
                model_snapshot_id=model.snapshot_id,
            )
        )
    return results
