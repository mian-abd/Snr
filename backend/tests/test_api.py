import shutil
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import REPOSITORY_ROOT, Settings
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


def _copy_evidence(data_dir) -> None:
    """Give a temporary data directory the committed sample and both saved matrices."""
    for relative in ("benchmarks", "demo/checkpoint-1", "demo/checkpoint-2-paid"):
        shutil.copytree(REPOSITORY_ROOT / "data" / relative, data_dir / relative)


class FakeRunner:
    def load_run(self, run_id: str):
        raise FileNotFoundError(run_id)


class FakeCoordinator:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.active_run_id: str | None = None

    @property
    def is_running(self) -> bool:
        return False

    def start(self, mode) -> str:
        self.started.append(mode.value)
        return f"gsm8k-paid-{mode.value}-test"


def test_read_only_endpoints_work_without_credential(
    registry, paid_registry, tmp_path
) -> None:
    _copy_evidence(tmp_path)
    settings = Settings(openrouter_api_key=None, data_dir=tmp_path)
    services = AppServices(
        settings=settings,
        registry=registry,
        generation_service=None,
        benchmark_runner=None,
        routing_registry=paid_registry,
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["credential_configured"] is False
        assert health.json()["routing_registry_snapshot_id"] == "openrouter-paid-2026-10-23-cp2"
        models = client.get("/api/v1/models")
        assert models.status_code == 200
        assert len(models.json()["models"]) == 2
        paid_models = client.get("/api/v1/models", params={"pool": "paid"})
        assert paid_models.status_code == 200
        assert len(paid_models.json()["models"]) == 3
        assert len(client.get("/api/v1/routing/models").json()["models"]) == 3
        eligibility = client.post("/api/v1/eligibility", json={"min_context_tokens": 500000})
        assert eligibility.status_code == 200
        rows = eligibility.json()["results"]
        assert [(item["pool"], item["eligible"]) for item in rows] == [
            ("baseline", False),
            ("baseline", True),
            ("paid", False),
            ("paid", True),
            ("paid", True),
        ]
        free_only = client.post(
            "/api/v1/eligibility", json={"min_context_tokens": 500000, "pool": "baseline"}
        )
        assert [item["eligible"] for item in free_only.json()["results"]] == [False, True]
        estimate = client.get(
            "/api/v1/benchmarks/gsm8k/estimate", params={"pool": "paid", "mode": "full"}
        )
        assert estimate.status_code == 200
        assert estimate.json()["cells"] == 36
        assert estimate.json()["requires_confirmation"] is True
        assert estimate.json()["within_cap"] is True
        free_estimate = client.get("/api/v1/benchmarks/gsm8k/estimate")
        assert free_estimate.json()["requires_confirmation"] is False
        assert free_estimate.json()["cells"] == 24
        paid_latest = client.get("/api/v1/benchmarks/runs/latest", params={"pool": "paid"})
        assert paid_latest.status_code == 200
        paid_run_id = paid_latest.json()["manifest"]["run_id"]
        assert paid_run_id.startswith("gsm8k-paid-full-")
        assert len(paid_latest.json()["summary"]["models"]) == 3
        paid_records = client.get(f"/api/v1/benchmarks/runs/{paid_run_id}/records")
        assert paid_records.status_code == 200
        assert paid_records.json()["total"] == 36
        free_latest = client.get("/api/v1/benchmarks/runs/latest")
        assert free_latest.status_code == 200
        assert len(free_latest.json()["summary"]["models"]) == 2
        lower_cost = client.post(
            "/api/v1/routing/decisions",
            json={"prompt": "Explain the water cycle.", "priority": "cost"},
        )
        assert lower_cost.status_code == 200
        assert lower_cost.json()["selected_model_id"].startswith("google/")
        constrained_quality = client.post(
            "/api/v1/routing/decisions",
            json={
                "prompt": "Explain the water cycle.",
                "priority": "cost",
                "min_context_tokens": 500000,
            },
        )
        assert constrained_quality.status_code == 200
        assert constrained_quality.json()["selected_model_id"].startswith("nvidia/")
        assert constrained_quality.json()["eligible_model_ids"] == [
            constrained_quality.json()["selected_model_id"]
        ]
        paid_quality = client.post(
            "/api/v1/routing/decisions",
            json={
                "prompt": "Explain the water cycle.",
                "priority": "quality",
                "pool": "paid",
            },
        )
        assert paid_quality.status_code == 200
        assert paid_quality.json()["selected_model_id"] == "google/gemini-4-argon"
        validation = client.get("/api/v1/routing/validation")
        assert validation.status_code == 200
        assert validation.json()["passed"] is True
        assert validation.json()["passed_cases"] == 5
        assert validation.json()["total_cases"] == 5
        paid_validation = client.get("/api/v1/routing/validation", params={"pool": "paid"})
        assert paid_validation.status_code == 200
        assert paid_validation.json()["strategy_id"] == "rule_based_paid_v1"
        assert paid_validation.json()["passed"] is True
        paid_dashboard = client.get("/api/v1/routing/dashboard", params={"pool": "paid"})
        assert paid_dashboard.status_code == 200
        assert paid_dashboard.json()["pool"] == "paid"
        assert len(paid_dashboard.json()["prompts"]) == 12
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


def test_paid_pool_comparison_calls_every_paid_model(
    monkeypatch, registry, paid_registry, tmp_path
) -> None:
    async def no_drift(_api_key: str | None = None) -> None:
        return None

    monkeypatch.setattr(paid_registry, "validate_live_catalog", no_drift)
    settings = Settings(openrouter_api_key="test-key", data_dir=tmp_path)
    services = AppServices(
        settings=settings,
        registry=registry,
        generation_service=FakeGenerationService(),  # type: ignore[arg-type]
        benchmark_runner=None,
        routing_registry=paid_registry,
        routing_generation_service=FakeGenerationService(),  # type: ignore[arg-type]
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        response = client.post(
            "/api/v1/comparisons", json={"prompt": "Explain this", "pool": "paid"}
        )
        assert response.status_code == 200
        assert response.json()["pool"] == "paid"
        assert [row["requested_model_id"] for row in response.json()["results"]] == [
            model.id for model in paid_registry.models
        ]


def test_paid_benchmark_requires_the_confirmed_estimate(
    monkeypatch, registry, paid_registry, tmp_path
) -> None:
    async def no_drift(_api_key: str | None = None) -> None:
        return None

    monkeypatch.setattr(paid_registry, "validate_live_catalog", no_drift)
    _copy_evidence(tmp_path)
    settings = Settings(openrouter_api_key="test-key", data_dir=tmp_path)
    coordinator = FakeCoordinator()
    services = AppServices(
        settings=settings,
        registry=registry,
        generation_service=FakeGenerationService(),  # type: ignore[arg-type]
        benchmark_runner=None,
        routing_registry=paid_registry,
        routing_generation_service=FakeGenerationService(),  # type: ignore[arg-type]
        paid_benchmark_runner=FakeRunner(),  # type: ignore[arg-type]
        paid_benchmark_coordinator=coordinator,  # type: ignore[arg-type]
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        estimate = client.get(
            "/api/v1/benchmarks/gsm8k/estimate", params={"pool": "paid", "mode": "pilot"}
        ).json()
        unconfirmed = client.post(
            "/api/v1/benchmarks/gsm8k/runs", json={"mode": "pilot", "pool": "paid"}
        )
        assert unconfirmed.status_code == 400
        stale = client.post(
            "/api/v1/benchmarks/gsm8k/runs",
            json={"mode": "pilot", "pool": "paid", "confirmed_estimate_usd": "0.0001"},
        )
        assert stale.status_code == 400
        assert coordinator.started == []
        confirmed = client.post(
            "/api/v1/benchmarks/gsm8k/runs",
            json={
                "mode": "pilot",
                "pool": "paid",
                "confirmed_estimate_usd": estimate["worst_case_usd"],
            },
        )
        assert confirmed.status_code == 202
        assert coordinator.started == ["pilot"]
        assert confirmed.json()["manifest"]["total_cells"] == 6
        assert confirmed.json()["manifest"]["model_ids"] == [m.id for m in paid_registry.models]
