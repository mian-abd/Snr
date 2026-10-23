import json

import pytest

from app.domain.models import EligibilityRequest
from app.registry.filtering import evaluate_eligibility
from app.registry.loader import ModelRegistry, RegistryError


def test_checkpoint_filter_excludes_only_gemma(registry: ModelRegistry) -> None:
    results = evaluate_eligibility(registry.models, EligibilityRequest(min_context_tokens=500_000))
    assert results[0].eligible is False
    assert results[0].reasons == ["context length 262144 < required 500000"]
    assert results[1].eligible is True
    assert results[1].reasons == ["all requirements satisfied"]


def test_filter_boundary_is_inclusive(registry: ModelRegistry) -> None:
    results = evaluate_eligibility(
        registry.models, EligibilityRequest(min_context_tokens=262_144)
    )
    assert results[0].eligible is True


def test_registry_rejects_tampered_checksum(registry: ModelRegistry, tmp_path) -> None:
    payload = registry.snapshot.model_dump(mode="json")
    payload["models"][0]["context_length"] = 1
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RegistryError, match="checksum"):
        ModelRegistry(path)


def test_paid_snapshots_differ_only_in_dated_gemma_price() -> None:
    from app.config import REPOSITORY_ROOT
    from app.state import PAID_MODEL_IDS

    def load(day: str) -> ModelRegistry:
        return ModelRegistry(
            REPOSITORY_ROOT / "data" / "registry" / f"openrouter-paid-2026-10-{day}.json",
            expected_model_ids=PAID_MODEL_IDS,
            require_free=False,
        )

    first, second = load("22"), load("23")
    changed = [
        new.id
        for old, new in zip(first.models, second.models, strict=True)
        if old.model_dump(exclude={"snapshot_id", "metadata_as_of"})
        != new.model_dump(exclude={"snapshot_id", "metadata_as_of"})
    ]
    assert changed == ["google/gemma-4-26b-a4b-it"]
    gemma = second.get("google/gemma-4-26b-a4b-it")
    assert str(gemma.pricing.prompt_per_token) == "9E-8"
    assert [model.id for model in second.models] == list(PAID_MODEL_IDS)
