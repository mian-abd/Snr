from pathlib import Path

import pytest

from app.registry.loader import ModelRegistry
from app.state import PAID_MODEL_IDS, PAID_REGISTRY_PATH

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry(REPOSITORY_ROOT / "data" / "registry" / "openrouter-2026-09-30.json")


@pytest.fixture
def paid_registry() -> ModelRegistry:
    return ModelRegistry(
        PAID_REGISTRY_PATH,
        expected_model_ids=PAID_MODEL_IDS,
        require_free=False,
    )
