import json
from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import REPOSITORY_ROOT, Settings
from app.domain.models import CostSource, GenerationOutcome, GenerationResult, GenerationStatus
from app.main import create_app
from app.providers import GenerationService
from app.providers.openai_compatible import OpenAICompatibleAdapter
from app.public import LiveCall, PublicGuard
from app.registry.loader import ModelRegistry
from app.registry.pool import endpoint_for
from app.state import REGISTRY_PATH, AppServices, build_learned_services

PROMPT = "Calculate 15 percent of 240."


class CountingService:
    """Answers every request and remembers which models were asked."""

    def __init__(self) -> None:
        self.models: list[str] = []

    async def generate_with_retries(self, request):
        self.models.append(request.model_id)
        now = datetime.now(UTC)
        result = GenerationResult(
            request_id=request.request_id, requested_model_id=request.model_id,
            served_model_id=request.model_id, status=GenerationStatus.SUCCESS, text="ok",
            latency_ms=1, cost_source=CostSource.UNAVAILABLE, started_at_utc=now,
            completed_at_utc=now, attempt_number=1,
        )
        return GenerationOutcome(final=result, attempts=[result])


def _client(registry, tmp_path, monkeypatch, **overrides) -> tuple[TestClient, CountingService]:
    async def no_drift(_api_key: str | None = None) -> None:
        return None

    monkeypatch.setattr(registry, "validate_live_catalog", no_drift)
    settings = Settings(openrouter_api_key="test-key", data_dir=tmp_path, **overrides)
    service = CountingService()
    services = AppServices(
        settings=settings, registry=registry,
        generation_service=service,  # type: ignore[arg-type]
        benchmark_runner=None,
    )
    return TestClient(create_app(settings=settings, services=services)), service


def _public(registry, tmp_path, monkeypatch, **overrides) -> tuple[TestClient, CountingService]:
    return _client(registry, tmp_path, monkeypatch, public_mode=True, **overrides)


def _compare(client: TestClient, **extra):
    return client.post("/api/v1/comparisons", json={"prompt": "Explain this", **extra})


def test_health_reports_the_calls_left(registry, tmp_path, monkeypatch) -> None:
    client, _ = _public(registry, tmp_path, monkeypatch)
    with client:
        health = client.get("/api/v1/health").json()
        assert health["public_mode"] is True
        assert (health["live_calls_left"], health["client_live_calls_left"]) == (60, 6)
        assert _compare(client).status_code == 200  # the baseline pool has two models
        health = client.get("/api/v1/health").json()
        assert (health["live_calls_left"], health["client_live_calls_left"]) == (58, 4)


def test_each_client_has_its_own_daily_cap(registry, tmp_path, monkeypatch) -> None:
    client, service = _public(registry, tmp_path, monkeypatch)
    with client:
        for _ in range(3):  # six calls, two per comparison
            assert _compare(client).status_code == 200
        refused = _compare(client)
        assert refused.status_code == 429
        assert "you have 0 of your 6 left" in refused.json()["detail"]
        assert len(service.models) == 6


def test_the_shared_cap_stops_everyone(registry, tmp_path, monkeypatch) -> None:
    client, service = _public(registry, tmp_path, monkeypatch, public_daily_live_calls=3)
    with client:
        assert _compare(client).status_code == 200  # two of three calls
        refused = _compare(client)  # needs two, one is left
        assert refused.status_code == 429
        assert "public demo has used its 3 live calls" in refused.json()["detail"]
        assert len(service.models) == 2
        assert client.get("/api/v1/health").json()["client_live_calls_left"] == 1


def test_allowances_reset_at_midnight_utc() -> None:
    today = [date(2026, 11, 26)]
    guard = PublicGuard(
        Settings(public_mode=True, public_client_daily_live_calls=2), lambda: today[0]
    )
    call = LiveCall("Model", "hi", 10, None, None)
    guard.admit("a", [call, call])
    assert (guard.shared_left(), guard.client_left("a"), guard.client_left("b")) == (58, 0, 2)
    today[0] = date(2026, 11, 27)
    assert (guard.shared_left(), guard.client_left("a")) == (60, 2)


def test_a_costly_call_is_refused_and_not_counted(tmp_path, monkeypatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["model"])
        return httpx.Response(500)

    settings = Settings(openrouter_api_key="test-key", data_dir=REPOSITORY_ROOT / "data",
                        public_mode=True)
    router, _ = build_learned_services(settings)
    assert router is not None
    adapter = OpenAICompatibleAdapter(
        [endpoint_for(model) for model in router.models.values()],
        transport=httpx.MockTransport(handler), keys={"OPENROUTER_API_KEY": "test-key"},
    )
    services = AppServices(
        settings=settings, registry=ModelRegistry(REGISTRY_PATH), generation_service=None,
        benchmark_runner=None, learned_router=router,
        learned_generation_service=GenerationService(adapter),
    )
    # Weights that care only about quality pick the flagship, whose output could cost far more.
    body = {"prompt": PROMPT, "weights": {"quality": 10, "cost": 0, "latency": 0}}
    with TestClient(create_app(settings=settings, services=services)) as client:
        preview = client.post("/api/v1/learned/decisions", json=body)
        assert preview.status_code == 200
        refused = client.post("/api/v1/learned/routes", json=body)
        assert refused.status_code == 403
        assert "Gemini 4 Argon" in refused.json()["detail"]
        assert "preview still shows the decision" in refused.json()["detail"]
        assert calls == []
        assert client.get("/api/v1/health").json()["live_calls_left"] == 60


def test_cost_limit_is_a_setting(registry, paid_registry, tmp_path, monkeypatch) -> None:
    async def no_drift(_api_key: str | None = None) -> None:
        return None

    monkeypatch.setattr(paid_registry, "validate_live_catalog", no_drift)
    settings = Settings(
        openrouter_api_key="test-key", data_dir=tmp_path, public_mode=True,
        public_max_call_usd="0.00001",
    )
    service = CountingService()
    services = AppServices(
        settings=settings, registry=registry, generation_service=service,  # type: ignore[arg-type]
        benchmark_runner=None, routing_registry=paid_registry,
        routing_generation_service=service,  # type: ignore[arg-type]
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        refused = client.post("/api/v1/comparisons", json={"prompt": "Explain", "pool": "paid"})
        assert refused.status_code == 403 and "could cost up to" in refused.json()["detail"]
        assert service.models == []


def test_benchmark_runs_are_refused(registry, tmp_path, monkeypatch) -> None:
    client, _ = _public(registry, tmp_path, monkeypatch)
    with client:
        response = client.post("/api/v1/benchmarks/gsm8k/runs", json={"mode": "pilot"})
        assert response.status_code == 403
        assert "turned off" in response.json()["detail"]


def test_saving_is_ignored(registry, tmp_path, monkeypatch) -> None:
    client, _ = _public(registry, tmp_path, monkeypatch)
    with client:
        response = _compare(client, save=True)
        assert response.status_code == 200
        assert response.json()["saved"] is False
        assert "not stored" in response.json()["note"]
        assert not (tmp_path / "local").exists()


def test_local_mode_is_unchanged(registry, tmp_path, monkeypatch) -> None:
    client, service = _client(registry, tmp_path, monkeypatch)
    with client:
        health = client.get("/api/v1/health").json()
        assert health["public_mode"] is False
        assert health["live_calls_left"] is None and health["client_live_calls_left"] is None
        for _ in range(5):  # ten calls, past both public limits
            assert _compare(client).status_code == 200
        saved = _compare(client, save=True).json()
        assert saved["saved"] is True and saved["note"] is None
        assert (tmp_path / "local" / "manual" / "comparisons.jsonl").exists()
        assert len(service.models) == 12
        # Benchmarks are not blocked by public mode (no runner here, so a 503, not a 403).
        started = client.post("/api/v1/benchmarks/gsm8k/runs", json={"mode": "pilot"})
        assert started.status_code == 503


@pytest.mark.parametrize("public", [True, False])
def test_catalog_refresh_is_limited_only_in_public_mode(tmp_path, public) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(404)

    settings = Settings(data_dir=REPOSITORY_ROOT / "data", public_mode=public,
                        live_catalog_check=True)
    router, _ = build_learned_services(settings)
    services = AppServices(
        settings=settings, registry=ModelRegistry(REGISTRY_PATH), generation_service=None,
        benchmark_runner=None, learned_router=router,
        catalog_transport=httpx.MockTransport(handler),
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        after_startup = len(requests)
        assert after_startup > 0  # the startup check
        assert client.post("/api/v1/learned/catalog/refresh").status_code == 200
        assert (len(requests) > after_startup) is (not public)
        assert services.catalog is not None
        services.catalog_refreshed_at = (services.catalog_refreshed_at or 0) - 601
        before = len(requests)
        assert client.post("/api/v1/learned/catalog/refresh").status_code == 200
        assert len(requests) > before
