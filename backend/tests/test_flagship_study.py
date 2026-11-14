import argparse
import asyncio

import pytest

from app.benchmarks.suite import RouterSplit, TaskGroup
from app.benchmarks.suite_runner import FLAGSHIP_POOL_PATH, POOL_PATH, run
from app.learned.features import Cell
from app.learned.flagship_study import combined_pool, strongest_flagship
from app.registry.pool import Access, load_pool, models_sha256


def _cell(model_id: str, sample: str, split: RouterSplit, correct: bool, cost: float) -> Cell:
    return Cell(
        sample_id=sample, model_id=model_id, task_group=TaskGroup.MATH, router_split=split,
        correct=correct, served=True, latency_ms=1000.0, completion_tokens=100, cost_usd=cost,
    )


def test_flagship_pool_is_paid_checksummed_and_pinned_to_one_host() -> None:
    pool = load_pool(FLAGSHIP_POOL_PATH)
    assert [model.id for model in pool.models] == [
        "gpt-6.1-sol", "gemini-4-carbon", "grok-4.7", "kimi-k3.1-pro",
    ]
    for model in pool.models:
        assert model.access == Access.PAID and model.prompt_price_per_token > 0
        provider = model.request_options["provider"]
        assert provider["allow_fallbacks"] is False and len(provider["order"]) == 1


def test_combined_pool_keeps_every_model_and_a_valid_checksum() -> None:
    base, flagships = load_pool(POOL_PATH), load_pool(FLAGSHIP_POOL_PATH)
    pool = combined_pool(base, flagships)
    assert pool.snapshot_id == "cp3-pool-2026-10-27+flagship-pool-2026-11-14"
    assert [model.id for model in pool.models] == [
        *(model.id for model in base.models), *(model.id for model in flagships.models),
    ]
    assert pool.models_sha256 == models_sha256(pool.models)


def test_strongest_flagship_counts_only_train_and_validation_and_breaks_ties_by_cost() -> None:
    cells = [
        # "a" and "b" tie on train + validation; "b" is cheaper. "c" wins only on test.
        _cell("a", "s1", RouterSplit.TRAIN, True, 0.02),
        _cell("a", "s2", RouterSplit.VALIDATION, True, 0.02),
        _cell("b", "s1", RouterSplit.TRAIN, True, 0.01),
        _cell("b", "s2", RouterSplit.VALIDATION, True, 0.01),
        _cell("c", "s1", RouterSplit.TRAIN, True, 0.001),
        _cell("c", "s2", RouterSplit.VALIDATION, False, 0.001),
        *(_cell("c", f"t{i}", RouterSplit.TEST, True, 0.001) for i in range(5)),
    ]
    assert strongest_flagship(cells, ["a", "b", "c"]) == "b"


@pytest.mark.parametrize("cap", ["0", "25.01", "100"])
def test_runner_refuses_a_spend_cap_outside_the_owner_ceiling(cap: str) -> None:
    args = argparse.Namespace(
        pool="flagship", suite="final", models=None, smoke=1, run_id="test-cap",
        free_used_today=0, confirm=False, spend_cap=cap,
    )
    with pytest.raises(SystemExit, match="spend-cap"):
        asyncio.run(run(args))


def _flagship_client(registry, tmp_path):
    import shutil

    from fastapi.testclient import TestClient

    from app.config import REPOSITORY_ROOT, Settings
    from app.learned.router import load_router
    from app.main import create_app
    from app.state import AppServices, build_flagship_services

    shutil.copytree(REPOSITORY_ROOT / "data" / "learned", tmp_path / "learned")
    shutil.copytree(REPOSITORY_ROOT / "data" / "registry", tmp_path / "registry")
    settings = Settings(openrouter_api_key="test-key", data_dir=tmp_path)
    flagship, _ = build_flagship_services(settings)
    standard = load_router(tmp_path / "learned" / "cp3-router-model.json", load_pool(POOL_PATH))
    services = AppServices(
        settings=settings, registry=registry, generation_service=None, benchmark_runner=None,
        learned_router=standard, flagship_router=flagship,
    )
    return TestClient(create_app(settings=settings, services=services)), flagship


def test_requests_route_over_the_pool_they_name(registry, tmp_path) -> None:
    client, flagship = _flagship_client(registry, tmp_path)
    assert flagship is not None
    flagships = set(flagship.pool_ids) - {
        model.id for model in load_pool(POOL_PATH).models
    }
    assert flagships and "grok-4.7" not in flagship.pool_ids  # stopped, so never routed
    prompt = "Which planet is known as the Red Planet?\nA. Venus\nB. Mars\nC. Jupiter\nD. Saturn"
    with client:
        standard = client.post("/api/v1/learned/decisions", json={"prompt": prompt})
        extended = client.post(
            "/api/v1/learned/decisions", json={"prompt": prompt, "pool": "flagships"}
        )
        report = client.get("/api/v1/learned/flagships")
    assert standard.status_code == 200 and extended.status_code == 200
    seen = {item["model_id"] for item in standard.json()["candidates"]}
    seen_extended = {item["model_id"] for item in extended.json()["candidates"]}
    assert not seen & flagships and flagships <= seen_extended
    assert report.status_code == 200
    assert [item["model_id"] for item in report.json()["excluded_flagships"]] == ["grok-4.7"]


def test_a_broken_flagship_router_leaves_the_standard_one_running(tmp_path) -> None:
    import shutil

    from app.config import REPOSITORY_ROOT, Settings
    from app.state import build_flagship_services

    shutil.copytree(REPOSITORY_ROOT / "data" / "registry", tmp_path / "registry")
    (tmp_path / "learned").mkdir()
    (tmp_path / "learned" / "flagship-router-model.json").write_text("{}", encoding="utf-8")
    assert build_flagship_services(Settings(data_dir=tmp_path)) == (None, None)
