import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.benchmarks.suite import TaskGroup
from app.config import REPOSITORY_ROOT, Settings
from app.domain.models import RoutingPriority
from app.domain.scoring_fix import ScoringFixReport
from app.learned import scoring_fix, validate
from app.learned.final_eval import load_suites
from app.learned.robustness import Knowledge, RouterView
from app.learned.router import ScoringReference, TaskEstimate, load_router
from app.main import create_app
from app.registry.pool import load_pool
from app.routing.multi_objective import (
    CandidateEstimate,
    PolicyWeights,
    score_candidates,
)
from app.state import AppServices

DATA = REPOSITORY_ROOT / "data"
POOL = load_pool(DATA / "registry" / "cp3-pool-2026-10-27.json")
WEIGHTS = PolicyWeights(quality=1.0, cost=1.0, latency=0.5, reliability=0.25)


def _candidates(gemini_price: float = 0.01) -> list[CandidateEstimate]:
    return [
        CandidateEstimate("cheap", 0.8, 0.001, 2000.0, 0.0),
        CandidateEstimate("free", 0.7, 0.0, 9000.0, 0.1),
        CandidateEstimate("strong", 0.95, gemini_price, 5000.0, 0.0),
    ]


def _terms(scored: list[Any]) -> dict[str, tuple[float, float]]:
    return {item.model_id: (item.cost_penalty, item.latency_penalty) for item in scored}


def test_the_default_still_divides_by_the_largest_available_value() -> None:
    scored = score_candidates(_candidates(), WEIGHTS)
    by_id = {item.model_id: item for item in scored}
    assert by_id["strong"].normalized_cost == 1.0
    assert by_id["free"].normalized_latency == 1.0
    assert by_id["cheap"].normalized_cost == pytest.approx(0.1)
    # Without a reference, passing None is the same call.
    again = score_candidates(_candidates(), WEIGHTS, cost_scale=None, latency_scale=None)
    assert _terms(again) == _terms(scored)


def test_a_fixed_reference_keeps_the_other_models_scores_when_one_price_changes() -> None:
    fixed = {"cost_scale": 0.01, "latency_scale": 9000.0}
    before = {item.model_id: item for item in score_candidates(_candidates(), WEIGHTS, **fixed)}
    after = {
        item.model_id: item
        for item in score_candidates(_candidates(gemini_price=0.04), WEIGHTS, **fixed)
    }
    assert after["strong"].normalized_cost == pytest.approx(4.0)  # no longer capped at 1
    for model in ("cheap", "free"):
        assert after[model].score == before[model].score
    # The frozen normalization shifts every other model's score instead.
    old_before = {item.model_id: item for item in score_candidates(_candidates(), WEIGHTS)}
    old_after = {
        item.model_id: item for item in score_candidates(_candidates(gemini_price=0.04), WEIGHTS)
    }
    assert old_after["strong"].normalized_cost == 1.0
    assert old_after["cheap"].score != old_before["cheap"].score


def test_a_reference_is_the_largest_estimate_per_task_group() -> None:
    estimates = {
        "a": {TaskGroup.MATH: TaskEstimate(
            expected_cost_usd=0.002, expected_latency_ms=5000.0, failure_rate=0.0)},
        "b": {TaskGroup.MATH: TaskEstimate(
            expected_cost_usd=0.01, expected_latency_ms=3000.0, failure_rate=0.1)},
    }
    reference = ScoringReference.from_estimates(estimates)
    assert reference.cost_usd == {TaskGroup.MATH: 0.01}
    assert reference.latency_ms == {TaskGroup.MATH: 5000.0}


def test_with_every_model_available_the_reference_picks_what_the_frozen_router_picks() -> None:
    router = load_router(DATA / "learned" / "cp3-router-model.json", POOL)
    suite = load_suites()["cp3"]
    prompts = sorted(suite.items)[:60]
    view = RouterView(router, suite.items, prompts)
    reference = ScoringReference.from_estimates(router.artifact.estimates)
    for priority in RoutingPriority:
        weights = router.artifact.weights[priority]
        for sample in prompts:
            assert view.choose(sample, weights, Knowledge(), reference) == view.choose(
                sample, weights, Knowledge()
            )


def test_the_fixed_questions_are_in_code_and_match_the_validator() -> None:
    ids = tuple(question.question_id for question in scoring_fix.FIXED_QUESTIONS)
    assert ids == validate.SCORING_FIX_QUESTIONS
    assert all(question.question.endswith("?") and question.rule
               for question in scoring_fix.FIXED_QUESTIONS)
    assert scoring_fix.FIXED_RELIABILITY_GRID[0] == scoring_fix.RELIABILITY_FLOOR > 0


@pytest.fixture(scope="module")
def report() -> ScoringFixReport:
    path = DATA / "learned" / "scoring-fix-study.json"
    return ScoringFixReport.model_validate_json(path.read_text(encoding="utf-8"))


def test_the_committed_report_answers_every_question_and_covers_the_gemma_scenario(
    report: ScoringFixReport,
) -> None:
    assert [item.question_id for item in report.questions] == list(validate.SCORING_FIX_QUESTIONS)
    assert report.tuning.frozen_recipe_reproduced
    assert all(item.weights.reliability >= scoring_fix.RELIABILITY_FLOOR
               for item in report.tuning.fixed_presets)
    assert [item.evaluation_id for item in report.evaluations] == ["cp3_test", "final"]
    for evaluation in report.evaluations:
        for router in (evaluation.frozen, evaluation.fixed):
            gone = next(item for item in router.scenarios
                        if item.scenario.scenario_id == scoring_fix.SCENARIO_GEMMA_GONE)
            assert gone.scenario.observed
            assert sorted(gone.scenario.unavailable) == ["gemma-4-26b", "mercury-3"]
            ids = {item.strategy_id for item in gone.strategies}
            for priority in RoutingPriority:
                assert {f"learned:{priority.value}", f"learned_frozen:{priority.value}"} <= ids


def test_the_frozen_router_file_and_final_report_are_untouched_by_the_study(
    report: ScoringFixReport,
) -> None:
    artifact = json.loads((DATA / "learned" / "cp3-router-model.json").read_text("utf-8"))
    frozen = {key: value for key, value in report.frozen_weights.items()}
    for priority, weights in artifact["weights"].items():
        assert frozen[RoutingPriority(priority)] == weights
    assert "reference" not in artifact  # the references live in the report, not the router


def _client(registry: Any, tmp_path: Path, *, with_report: bool = True) -> TestClient:
    shutil.copytree(DATA / "learned", tmp_path / "learned")
    if not with_report:
        (tmp_path / "learned" / "scoring-fix-study.json").unlink()
    settings = Settings(openrouter_api_key="test-key", data_dir=tmp_path)
    services = AppServices(
        settings=settings, registry=registry, generation_service=None, benchmark_runner=None,
        learned_router=None,
    )
    return TestClient(create_app(settings=settings, services=services))


def test_the_endpoint_serves_the_typed_report(registry: Any, tmp_path: Path) -> None:
    with _client(registry, tmp_path) as client:
        response = client.get("/api/v1/learned/scoring-fix")
        assert response.status_code == 200
        body = response.json()
        assert body["study_id"] == "scoring-fix"
        assert len(body["questions"]) == 4
        assert {item["evaluation_id"] for item in body["evaluations"]} == {"cp3_test", "final"}
        ScoringFixReport.model_validate(body)


def test_the_scoring_fix_is_an_export_table(registry: Any, tmp_path: Path) -> None:
    with _client(registry, tmp_path) as client:
        response = client.get("/api/v1/learned/export/scoring_fix", params={"format": "csv"})
        assert response.status_code == 200
        lines = response.text.splitlines()
        assert lines[0].startswith("evaluation,scoring,scenario,title")
        assert any(",gemma_mercury_unavailable," in line for line in lines)
        assert {"frozen", "fixed"} <= {line.split(",")[1] for line in lines[1:]}


def test_the_endpoint_is_404_before_the_study_has_run(registry: Any, tmp_path: Path) -> None:
    with _client(registry, tmp_path, with_report=False) as client:
        assert client.get("/api/v1/learned/scoring-fix").status_code == 404


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "data"
    for folder in ("benchmarks", "learned", "registry"):
        shutil.copytree(DATA / folder, copy / folder)
    return copy


def test_the_validator_checks_the_scoring_fix_report_and_catches_a_wrong_baseline(
    data_copy: Path,
) -> None:
    names = {check.name for check in validate.run(data_copy) if check.passed}
    assert {
        "learned/scoring-fix-study.json final matrix",
        "learned/scoring-fix-study.json baselines",
        "learned/scoring-fix-study.json questions",
    } <= names
    path = data_copy / "learned" / "scoring-fix-study.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    scenario = next(item for item in body["evaluations"][1]["fixed"]["scenarios"]
                    if item["scenario"]["scenario_id"] == "no_change")
    next(item for item in scenario["strategies"]
         if item["strategy_id"] == "fixed_strongest")["correct"] += 1
    body["evaluations"][0]["matrix"][0]["correct"] += 1
    path.write_text(json.dumps(body), encoding="utf-8")
    failed = {check.name for check in validate.run(data_copy) if not check.passed}
    assert "learned/scoring-fix-study.json baselines" in failed
    assert "learned/scoring-fix-study.json cp3_test matrix" in failed
