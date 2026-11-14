import asyncio
import shutil
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from app.benchmarks.suite import load_suite
from app.config import REPOSITORY_ROOT, Settings
from app.domain.models import (
    CatalogSource,
    LearnedRouteRequest,
    ModelSpec,
    RoutingPriority,
)
from app.learned.router import ROUTER_MODEL_PATH, live_expected_cost, load_router
from app.main import create_app
from app.registry.live_catalog import check_live_catalog, listed_status, openrouter_status
from app.registry.loader import drift_problems
from app.registry.pool import load_pool
from app.state import AppServices

POOL = load_pool(REPOSITORY_ROOT / "data" / "registry" / "cp3-pool-2026-10-27.json")
BY_ID = {model.id: model for model in POOL.models}
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def endpoints(*hosts: tuple[str, str, str]) -> dict:
    return {"data": {"endpoints": [
        {"tag": tag, "pricing": {"prompt": prompt, "completion": completion}}
        for tag, prompt, completion in hosts
    ]}}


def fake_providers(request: httpx.Request) -> httpx.Response:
    """Today's catalog as observed on 2026-11-13, served without the network."""
    url = str(request.url)
    if "inception/mercury-3" in url:
        return httpx.Response(200, json={"data": {"id": "inception/mercury-3", "endpoints": []}})
    if "gemma-4-26b" in url:
        return httpx.Response(200, json=endpoints(("nextbit/bf16", "0.0000000675", "0.000000225")))
    if "deepseek-v4-flash" in url:
        return httpx.Response(200, json=endpoints(
            ("parasail/fp8", "0.00000014", "0.00000028"),
            ("deepinfra/fp8", "0.00000009", "0.00000018"),
        ))
    if "gemini-4-argon" in url:
        return httpx.Response(200, json=endpoints(("google-ai-studio", "0.000002", "0.00001")))
    if "nemotron" in url:
        return httpx.Response(200, json=endpoints(("nvidia", "0", "0")))
    if "ovh.net" in url:
        return httpx.Response(200, json={"data": [
            {"id": "gpt-oss-120b"}, {"id": "Meta-Llama-3_3-70B-Instruct"}, {"id": "Qwen3.8-27B"},
        ]})
    if "localhost:11434" in url:
        return httpx.Response(200, json={"data": [{"id": "qwen3.5-9b-cp3:latest"}]})
    return httpx.Response(500)


def router_models():
    return load_router(ROUTER_MODEL_PATH, POOL).models.values()


def test_openrouter_retirement_price_change_and_lost_host() -> None:
    gone = openrouter_status(BY_ID["mercury-3"], httpx.Response(
        200, json={"data": {"endpoints": []}}, request=httpx.Request("GET", "https://x")
    ))
    assert not gone.available and gone.checked and "retired" in gone.note
    delisted = openrouter_status(
        BY_ID["mercury-3"], httpx.Response(404, request=httpx.Request("GET", "https://x"))
    )
    assert not delisted.available and "no longer lists" in delisted.note
    gemma = openrouter_status(BY_ID["gemma-4-26b"], httpx.Response(
        200, json=endpoints(("nextbit/bf16", "0.0000000675", "0.000000225")),
        request=httpx.Request("GET", "https://x"),
    ))
    assert gemma.available
    assert round(gemma.live_prompt_price_per_million or 0, 4) == 0.0675
    assert "$0.0765 / $0.255 to $0.0675 / $0.225" in gemma.note
    deepseek = openrouter_status(BY_ID["deepseek-v4-flash"], httpx.Response(
        200,
        json=endpoints(("parasail/fp8", "0.00000014", "0.00000028"),
                       ("deepinfra/fp8", "0.00000009", "0.00000018")),
        request=httpx.Request("GET", "https://x"),
    ))
    # The highest remaining pinned price is the snapshot's, so only the lost host is news.
    assert deepseek.available and deepseek.missing_hosts == ["crusoe/fp8"]
    assert deepseek.note == "Pinned host crusoe/fp8 no longer serves it"
    unpinned = openrouter_status(BY_ID["gemma-4-26b"], httpx.Response(
        200, json=endpoints(("someone-else", "0.0000001", "0.0000003")),
        request=httpx.Request("GET", "https://x"),
    ))
    assert not unpinned.available and "nextbit/bf16" in unpinned.note


def test_listed_providers_and_local_server() -> None:
    assert listed_status(BY_ID["qwen-3.5-9b-local"], {"qwen3.5-9b-cp3:latest"}).available
    dropped = listed_status(BY_ID["llama-3.3-70b"], {"gpt-oss-120b"})
    assert not dropped.available and "OVHcloud endpoint no longer lists" in dropped.note

    def ollama_down(request: httpx.Request) -> httpx.Response:
        if "localhost" in str(request.url):
            raise httpx.ConnectError("refused", request=request)
        return fake_providers(request)

    status = asyncio.run(check_live_catalog(
        router_models(), POOL, transport=httpx.MockTransport(ollama_down), now=NOW
    ))
    local = next(item for item in status.models if item.model_id == "qwen-3.5-9b-local")
    assert not local.available and local.note == "The local Ollama server is not running"


def test_full_check_and_snapshot_fallback() -> None:
    status = asyncio.run(check_live_catalog(
        router_models(), POOL, transport=httpx.MockTransport(fake_providers), now=NOW
    ))
    assert status.source == CatalogSource.LIVE and status.error is None
    unavailable = [item.model_id for item in status.models if not item.available]
    assert unavailable == ["mercury-3"]
    assert all(item.checked for item in status.models)

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("offline", request=request)

    fallback = asyncio.run(check_live_catalog(
        router_models(), POOL, transport=httpx.MockTransport(offline), now=NOW
    ))
    assert fallback.source == CatalogSource.SNAPSHOT and fallback.error
    # A failed check never removes a model: everything stays as the snapshot describes it.
    assert all(item.available and not item.checked for item in fallback.models)


def test_router_excludes_retired_models_and_reprices() -> None:
    router = load_router(ROUTER_MODEL_PATH, POOL)
    catalog = asyncio.run(check_live_catalog(
        router.models.values(), POOL, transport=httpx.MockTransport(fake_providers), now=NOW
    ))
    prompt = "A train travels 180 km in 2.5 hours. What is its average speed in km/h?"
    request = LearnedRouteRequest(prompt=prompt, priority=RoutingPriority.LATENCY)
    keys = {"OPENROUTER_API_KEY"}
    unaware = router.decide(request, keys)
    assert unaware.selected_model_id == "mercury-3"
    assert unaware.catalog_source == CatalogSource.OFF
    aware = router.decide(request, keys, catalog)
    assert aware.selected_model_id != "mercury-3"
    assert aware.catalog_source == CatalogSource.LIVE
    by_id = {item.model_id: item for item in aware.candidates}
    assert not by_id["mercury-3"].eligible
    assert (by_id["mercury-3"].exclusion_reason or "").startswith("Unavailable now: OpenRouter")
    assert "Without the live catalog check it would have chosen Mercury 3" in aware.reason
    gemma = by_id["gemma-4-26b"]
    assert gemma.snapshot_expected_cost_usd is not None
    assert abs(gemma.expected_cost_usd / gemma.snapshot_expected_cost_usd - 0.0675 / 0.0765) < 1e-9
    assert gemma.catalog_note and "Price changed" in gemma.catalog_note
    assert by_id["gemini-4-argon"].snapshot_expected_cost_usd is None
    assert by_id["gemini-4-argon"].catalog_note is None


def test_live_expected_cost_handles_free_and_unchanged_models() -> None:
    assert live_expected_cost(0.001, None, 100, 200) == 0.001
    status = asyncio.run(check_live_catalog(
        router_models(), POOL, transport=httpx.MockTransport(fake_providers), now=NOW
    ))
    nemotron = next(item for item in status.models if item.model_id == "nemotron-3-ultra-free")
    assert live_expected_cost(0.0, nemotron, 100, 200) == 0.0
    charging = nemotron.model_copy(update={
        "live_prompt_price_per_million": 1.0, "live_completion_price_per_million": 2.0,
    })
    assert abs(live_expected_cost(0.0, charging, 100, 200) - 500 / 1_000_000) < 1e-12


def test_catalog_endpoints_report_and_refresh(registry, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LIVE_CATALOG_CHECK", "true")
    shutil.copytree(REPOSITORY_ROOT / "data" / "learned", tmp_path / "learned")
    shutil.copytree(REPOSITORY_ROOT / "data" / "registry", tmp_path / "registry")
    settings = Settings(openrouter_api_key="test-key", data_dir=tmp_path)
    assert settings.live_catalog_check is True
    services = AppServices(
        settings=settings, registry=registry, generation_service=None, benchmark_runner=None,
        learned_router=load_router(tmp_path / "learned" / "cp3-router-model.json", POOL),
        catalog_transport=httpx.MockTransport(fake_providers),
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        status = client.get("/api/v1/learned/catalog").json()
        assert status["source"] == "live"
        assert [m["model_id"] for m in status["models"] if not m["available"]] == ["mercury-3"]
        decision = client.post("/api/v1/learned/decisions", json={
            "prompt": "A train travels 180 km in 2.5 hours. What is its average speed in km/h?",
            "priority": "latency",
        }).json()
        assert decision["selected_model_id"] != "mercury-3"
        assert decision["catalog_source"] == "live"
        assert "would have chosen Mercury 3" in decision["reason"]
        refreshed = client.post("/api/v1/learned/catalog/refresh")
        assert refreshed.status_code == 200 and refreshed.json()["source"] == "live"


def test_catalog_disabled_reports_off(registry, tmp_path) -> None:
    shutil.copytree(REPOSITORY_ROOT / "data" / "learned", tmp_path / "learned")
    settings = Settings(openrouter_api_key=None, data_dir=tmp_path)
    services = AppServices(
        settings=settings, registry=registry, generation_service=None, benchmark_runner=None,
        learned_router=load_router(tmp_path / "learned" / "cp3-router-model.json", POOL),
    )
    with TestClient(create_app(settings=settings, services=services)) as client:
        status = client.get("/api/v1/learned/catalog").json()
        assert status["source"] == "off" and status["models"] == []


def test_checkpoint2_drift_message_lists_every_change() -> None:
    frozen = [
        ModelSpec.model_validate({
            "id": "inception/mercury-3", "display_name": "Inception: Mercury 3",
            "provider": "inception", "context_length": 1000000,
            "pricing": {"prompt_per_token": "0.0000001", "completion_per_token": "0.00000035"},
            "input_modalities": ["text"], "output_modalities": ["text"],
            "supported_parameters": [], "capabilities": {}, "enabled": True,
            "snapshot_id": "s", "metadata_as_of": "2026-10-23T00:00:00Z", "source_url": "u",
        }),
        ModelSpec.model_validate({
            "id": "google/gemma-4-26b-a4b-it", "display_name": "Google: Gemma 4 26B A4B",
            "provider": "google", "context_length": 262144,
            "pricing": {"prompt_per_token": "0.00000009", "completion_per_token": "0.0000003"},
            "input_modalities": ["text"], "output_modalities": ["text"],
            "supported_parameters": [], "capabilities": {}, "enabled": True,
            "snapshot_id": "s", "metadata_as_of": "2026-10-23T00:00:00Z", "source_url": "u",
        }),
    ]
    live = {"google/gemma-4-26b-a4b-it": {
        "architecture": {"output_modalities": ["text"]}, "context_length": 262144,
        "pricing": {"prompt": "0.0000000675", "completion": "0.000000225"},
    }}
    problems = drift_problems(frozen, live, require_free=False)
    assert problems[0] == (
        "Inception: Mercury 3 (inception/mercury-3) is no longer served by OpenRouter (retired)"
    )
    assert "changed price from $0.09 / $0.3 to $0.0675 / $0.225 per million" in problems[1]


def test_bare_provider_pins_and_malformed_answers() -> None:
    # A bare slug in the pinned order covers every endpoint of that provider.
    mercury = openrouter_status(BY_ID["mercury-3"], httpx.Response(
        200, json=endpoints(("inception/fp8", "0.0000001", "0.00000035")),
        request=httpx.Request("GET", "https://x"),
    ))
    assert mercury.available and mercury.serving_hosts == ["inception/fp8"]
    # An exact pin ignores the same provider's other service tiers and their prices.
    gemini = openrouter_status(BY_ID["gemini-4-argon"], httpx.Response(
        200, json=endpoints(("google-ai-studio", "0.000002", "0.00001"),
                            ("google-ai-studio/priority", "0.0000036", "0.000018")),
        request=httpx.Request("GET", "https://x"),
    ))
    assert gemini.serving_hosts == ["google-ai-studio"]
    assert gemini.note == "Served by its pinned host; price unchanged"

    def odd(request: httpx.Request) -> httpx.Response:
        if "gemini" in str(request.url):
            return httpx.Response(200, json=["not", "an", "object"])
        if "gemma-4-26b" in str(request.url):
            return httpx.Response(200, json={"data": {"endpoints": [
                {"tag": "nextbit/bf16", "pricing": None},
            ]}})
        return fake_providers(request)

    status = asyncio.run(check_live_catalog(
        router_models(), POOL, transport=httpx.MockTransport(odd), now=NOW
    ))
    by_id = {item.model_id: item for item in status.models}
    # One malformed answer does not throw away the other providers' answers.
    assert status.source == CatalogSource.LIVE
    assert not by_id["mercury-3"].available
    gemma = by_id["gemma-4-26b"]
    assert gemma.available and gemma.live_prompt_price_per_million is None
    gemini = by_id["gemini-4-argon"]
    assert gemini.available and not gemini.checked


def test_reason_only_calls_a_model_retired_when_it_is() -> None:
    router = load_router(ROUTER_MODEL_PATH, POOL)
    catalog = asyncio.run(check_live_catalog(
        router.models.values(), POOL, transport=httpx.MockTransport(fake_providers), now=NOW
    ))
    keys = {"OPENROUTER_API_KEY"}
    items = load_suite(REPOSITORY_ROOT / "data" / "benchmarks" / "final_heldout.jsonl")
    for item in items[::5]:
        for priority in RoutingPriority:
            decision = router.decide(
                LearnedRouteRequest(prompt=item.question, priority=priority), keys, catalog
            )
            if "which is no longer served" in decision.reason:
                assert "Mercury 3" in decision.reason
    # Without a key, Mercury is excluded anyway, so the catalog cannot be what changed the pick.
    keyless = router.decide(
        LearnedRouteRequest(prompt="A train travels 180 km in 2.5 hours. What is its average "
                            "speed in km/h?", priority=RoutingPriority.LATENCY), set(), catalog,
    )
    assert "no longer served" not in keyless.reason
