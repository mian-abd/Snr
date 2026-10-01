from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.models import (
    CostSource,
    GenerationOutcome,
    GenerationResult,
    GenerationStatus,
)
from app.main import create_app
from app.state import AppServices


class FakeGenerationService:
    async def generate_with_retries(self, request):
        now = datetime.now(UTC)
        failed = request.model_id.startswith("nvidia/")
        result = GenerationResult(
            request_id=request.request_id,
            requested_model_id=request.model_id,
            served_model_id=None if failed else request.model_id,
            status=GenerationStatus.PROVIDER_ERROR if failed else GenerationStatus.SUCCESS,
            text=None if failed else "A useful response",
            prompt_tokens=None if failed else 4,
            completion_tokens=None if failed else 3,
            total_tokens=None if failed else 7,
            latency_ms=12,
            cost_usd=None,
            cost_source=CostSource.UNAVAILABLE,
            provider_request_id="must-not-reach-browser",
            error_code="503" if failed else None,
            error_message="temporary failure" if failed else None,
            started_at_utc=now,
            completed_at_utc=now,
            attempt_number=1,
        )
        return GenerationOutcome(final=result, attempts=[result])


def test_read_only_endpoints_work_without_credential(registry, tmp_path) -> None:
    settings = Settings(openrouter_api_key=None, data_dir=tmp_path)
    services = AppServices(
        settings=settings,
        registry=registry,
        generation_service=None,
        benchmark_runner=None,
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["credential_configured"] is False
        models = client.get("/api/v1/models")
        assert models.status_code == 200
        assert len(models.json()["models"]) == 2
        eligibility = client.post("/api/v1/eligibility", json={"min_context_tokens": 500000})
        assert eligibility.status_code == 200
        assert [item["eligible"] for item in eligibility.json()["results"]] == [False, True]
        compare = client.post("/api/v1/comparisons", json={"prompt": "hello", "save": False})
        assert compare.status_code == 503


def test_blank_prompt_is_rejected(registry, tmp_path) -> None:
    settings = Settings(openrouter_api_key=None, data_dir=tmp_path)
    services = AppServices(
        settings=settings,
        registry=registry,
        generation_service=None,
        benchmark_runner=None,
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        response = client.post("/api/v1/comparisons", json={"prompt": "   ", "save": False})
        assert response.status_code == 422


def test_comparison_preserves_partial_success_and_save_is_opt_in(
    monkeypatch, registry, tmp_path
) -> None:
    async def no_drift(_api_key: str | None = None) -> None:
        return None

    monkeypatch.setattr(registry, "validate_live_catalog", no_drift)
    settings = Settings(openrouter_api_key="test-key", data_dir=tmp_path)
    services = AppServices(
        settings=settings,
        registry=registry,
        generation_service=FakeGenerationService(),  # type: ignore[arg-type]
        benchmark_runner=None,
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        unsaved = client.post(
            "/api/v1/comparisons", json={"prompt": "Explain this", "save": False}
        )
        assert unsaved.status_code == 200
        assert [row["status"] for row in unsaved.json()["results"]] == [
            "success",
            "provider_error",
        ]
        assert all(row["provider_request_id"] is None for row in unsaved.json()["results"])
        assert not (tmp_path / "local" / "manual" / "comparisons.jsonl").exists()

        saved = client.post(
            "/api/v1/comparisons", json={"prompt": "Explain this", "save": True}
        )
        assert saved.status_code == 200
        assert (tmp_path / "local" / "manual" / "comparisons.jsonl").exists()
