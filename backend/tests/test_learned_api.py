import csv
import io
import shutil

from fastapi.testclient import TestClient

from app.config import REPOSITORY_ROOT, Settings
from app.learned.router import load_router
from app.main import create_app
from app.registry.pool import load_pool
from app.state import AppServices

POOL = load_pool(REPOSITORY_ROOT / "data" / "registry" / "cp3-pool-2026-10-27.json")
DEMO = "A train travels 180 km in 2.5 hours. What is its average speed in km/h?"


def _client(registry, tmp_path, *, with_router: bool = True) -> TestClient:
    shutil.copytree(REPOSITORY_ROOT / "data" / "learned", tmp_path / "learned")
    settings = Settings(openrouter_api_key="test-key", data_dir=tmp_path)
    router = load_router(tmp_path / "learned" / "cp3-router-model.json", POOL)
    services = AppServices(
        settings=settings, registry=registry, generation_service=None, benchmark_runner=None,
        learned_router=router if with_router else None,
    )
    return TestClient(create_app(settings=settings, services=services))


def test_final_report_and_every_export(registry, tmp_path) -> None:
    with _client(registry, tmp_path) as client:
        report = client.get("/api/v1/learned/final")
        assert report.status_code == 200
        body = report.json()
        assert [item["evaluation_id"] for item in body["evaluations"]] == ["cp3_test", "final"]
        assert body["evaluations"][0]["prompts"] == 120
        for table in ("strategies", "comparisons", "errors", "robustness", "sweep",
                      "decisions", "cells"):
            response = client.get(f"/api/v1/learned/export/{table}", params={"format": "csv"})
            assert response.status_code == 200, table
            assert response.headers["content-type"].startswith("text/csv")
            assert f'filename="router-{table}.csv"' in response.headers["content-disposition"]
            rows = list(csv.DictReader(io.StringIO(response.text)))
            assert rows, table
            as_json = client.get(f"/api/v1/learned/export/{table}", params={"format": "json"})
            assert as_json.status_code == 200 and len(as_json.json()) == len(rows)
        strategies = client.get("/api/v1/learned/export/strategies").text
        assert "accuracy_ci_low" in strategies.splitlines()[0]
        cells = client.get("/api/v1/learned/export/cells").text
        assert "text" not in cells.splitlines()[0].split(",")  # outcomes only, no responses
        assert client.get("/api/v1/learned/export/secrets").status_code == 404
        assert client.get(
            "/api/v1/learned/export/cells", params={"format": "xml"}
        ).status_code == 422


def test_missing_final_report_is_not_found(registry, tmp_path) -> None:
    with _client(registry, tmp_path) as client:
        (tmp_path / "learned" / "final-evaluation.json").unlink()
        assert client.get("/api/v1/learned/final").status_code == 404
        assert client.get("/api/v1/learned/export/strategies").status_code == 404


def test_pool_registry_lists_every_model(registry, tmp_path) -> None:
    with _client(registry, tmp_path) as client:
        pool = client.get("/api/v1/learned/pool").json()
        assert pool["snapshot_id"] == "cp3-pool-2026-10-27"
        assert len(pool["models"]) == 11
        gemini = next(model for model in pool["models"] if model["id"] == "gemini-4-argon")
        assert gemini["context_length"] == 1048576 and gemini["access"] == "paid"


def test_what_if_shows_how_a_changed_condition_moves_the_decision(registry, tmp_path) -> None:
    with _client(registry, tmp_path) as client:
        route = {"prompt": DEMO, "priority": "latency"}
        slower = client.post("/api/v1/learned/what-if", json={
            "route": route, "changes": {"latency_multipliers": {"mercury-3": 10}},
        })
        assert slower.status_code == 200
        body = slower.json()
        assert body["before"]["selected_model_id"] == "mercury-3"
        assert body["after"]["selected_model_id"] != "mercury-3" and body["changed"] is True
        notes = {item["model_id"]: item["what_if_note"] for item in body["after"]["candidates"]}
        assert notes["mercury-3"] == "latency x10" and notes["gemma-4-26b"] is None
        gone = client.post("/api/v1/learned/what-if", json={
            "route": route, "changes": {"unavailable": ["mercury-3"]},
        }).json()
        mercury = next(
            item for item in gone["after"]["candidates"] if item["model_id"] == "mercury-3"
        )
        assert mercury["exclusion_reason"] == "What-if: marked unavailable"
        same = client.post("/api/v1/learned/what-if", json={"route": route, "changes": {}})
        assert same.json()["changed"] is False
        unknown = client.post("/api/v1/learned/what-if", json={
            "route": route, "changes": {"price_multipliers": {"not-a-model": 2}},
        })
        assert unknown.status_code == 422
        invalid = client.post("/api/v1/learned/what-if", json={
            "route": route, "changes": {"price_multipliers": {"gemma-4-26b": 0}},
        })
        assert invalid.status_code == 422


def test_learned_endpoints_need_the_router(registry, tmp_path) -> None:
    with _client(registry, tmp_path, with_router=False) as client:
        assert client.get("/api/v1/learned/pool").status_code == 503
        assert client.post("/api/v1/learned/what-if", json={
            "route": {"prompt": DEMO}, "changes": {},
        }).status_code == 503
