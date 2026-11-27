import shutil

from fastapi.testclient import TestClient

from app.config import REPOSITORY_ROOT, Settings
from app.domain.explorer import ExplorerEvaluation
from app.learned.explorer import build_explorer
from app.main import create_app
from app.state import AppServices
from app.storage import read_jsonl

BASE_MODELS = 9
FLAGSHIPS = {"gpt-6.1-sol", "gemini-4-carbon", "kimi-k3.1-pro"}
BUDGET = {
    "gpt-6-luna", "mimo-v2.6-flash", "muse-ember", "ministral-8b", "ernie-5.5-flash-free",
}


def _copy_data(data_dir) -> None:
    """The committed prompt sets, cell tables, decisions, and registries, in a scratch folder."""
    for relative in ("benchmarks", "learned", "registry"):
        shutil.copytree(REPOSITORY_ROOT / "data" / relative, data_dir / relative)


def _client(registry, data_dir) -> TestClient:
    settings = Settings(openrouter_api_key=None, data_dir=data_dir)
    services = AppServices(
        settings=settings, registry=registry, generation_service=None, benchmark_runner=None
    )
    return TestClient(create_app(settings=settings, services=services))


def test_explorer_joins_each_prompt_with_every_model_and_choice(registry, tmp_path) -> None:
    _copy_data(tmp_path)
    with _client(registry, tmp_path) as client:
        response = client.get("/api/v1/learned/prompts")
        assert response.status_code == 200
        assert response.headers["content-encoding"] == "gzip"  # about a tenth of the raw JSON
        body = response.json()

        assert body["evaluation"] == "final"
        assert len(body["prompts"]) == 300
        models = {model["model_id"]: model for model in body["models"]}
        assert len(models) == BASE_MODELS + len(FLAGSHIPS) + len(BUDGET)
        added = {key: model["added_from"] for key, model in models.items() if model["added_from"]}
        assert added == {
            **dict.fromkeys(FLAGSHIPS, "flagship"), **dict.fromkeys(BUDGET, "budget"),
        }
        assert models["qwen-3.5-9b-local"]["access"] == "local"
        assert models["gemini-4-argon"]["display_name"] == "Gemini 4 Argon"
        # Models stopped part-way are listed as left out, never as a column.
        assert [model["model_id"] for model in body["excluded"]] == ["grok-4.7"]
        assert len(body["strategies"]) == 20 and "learned:quality" in body["strategies"]

        decisions = {
            (row["sample_id"], row["strategy"]): row
            for row in read_jsonl(tmp_path / "learned" / "final-decisions.jsonl")
            if row["evaluation"] == "final"
        }
        for prompt in body["prompts"]:
            assert set(prompt["outcomes"]) == set(models)
            assert set(prompt["choices"]) == set(body["strategies"])
            for outcome in prompt["outcomes"].values():
                assert isinstance(outcome["latency_ms"], int)
                assert round(outcome["cost_usd"], 7) == outcome["cost_usd"]
                assert outcome["status"] == "success" or not outcome["correct"]
            for strategy, model_id in prompt["choices"].items():
                decision = decisions[(prompt["sample_id"], strategy)]
                assert decision["model_id"] == model_id
                assert prompt["outcomes"][model_id]["correct"] == decision["correct"]

        by_benchmark = {prompt["benchmark"]: prompt for prompt in body["prompts"]}
        assert by_benchmark["gsm8k"]["expected_answer"].strip()
        choice = by_benchmark["mmlu_pro"]
        assert choice["options"] and choice["expected_answer"] in "ABCDEFGHIJ"
        code = by_benchmark["mbpp_plus"]
        assert code["expected_answer"] is None and "MBPP+" in code["answer_note"]

        original = client.get("/api/v1/learned/prompts", params={"evaluation": "cp3_test"})
        assert original.status_code == 200
        assert len(original.json()["prompts"]) == 120
        assert len(original.json()["strategies"]) == 15
        assert client.get(
            "/api/v1/learned/prompts", params={"evaluation": "train"}
        ).status_code == 422


def test_explorer_skips_a_missing_table_and_rebuilds_when_it_lands(tmp_path) -> None:
    _copy_data(tmp_path)
    flagship_cells = tmp_path / "learned" / "flagship-cells.jsonl"
    held = tmp_path / "flagship-cells.jsonl"
    flagship_cells.rename(held)
    (tmp_path / "learned" / "budget-cells.jsonl").unlink()
    before = build_explorer(tmp_path, ExplorerEvaluation.FINAL)
    assert len(before.models) == BASE_MODELS and before.excluded == []
    assert build_explorer(tmp_path, ExplorerEvaluation.FINAL) is before  # served from the cache

    held.rename(flagship_cells)
    after = build_explorer(tmp_path, ExplorerEvaluation.FINAL)
    assert {model.model_id for model in after.models} >= FLAGSHIPS


def test_missing_prompt_set_is_not_found(registry, tmp_path) -> None:
    _copy_data(tmp_path)
    (tmp_path / "benchmarks" / "cp3_suite.jsonl").unlink()
    with _client(registry, tmp_path) as client:
        assert client.get(
            "/api/v1/learned/prompts", params={"evaluation": "cp3_test"}
        ).status_code == 404
        assert client.get("/api/v1/learned/prompts").status_code == 200
