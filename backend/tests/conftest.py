from pathlib import Path

import pytest

from app.registry.loader import ModelRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry(REPOSITORY_ROOT / "data" / "registry" / "openrouter-2026-09-30.json")
