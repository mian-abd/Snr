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
