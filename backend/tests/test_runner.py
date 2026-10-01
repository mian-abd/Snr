from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.benchmarks.runner import BenchmarkRunner
from app.domain.models import (
    BenchmarkMode,
    CostSource,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.providers.service import GenerationService


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(
        self, request: GenerationRequest, *, attempt_number: int = 1
    ) -> GenerationResult:
        self.calls.append(request.model_id)
        answer = "109" if "Darrell" in request.prompt else "8"
        now = datetime.now(UTC)
        return GenerationResult(
            request_id=request.request_id,
            requested_model_id=request.model_id,
            served_model_id=request.model_id,
            status=GenerationStatus.SUCCESS,
            text=f"Reasoning\nFINAL_ANSWER: {answer}",
            prompt_tokens=20,
            completion_tokens=5,
            total_tokens=25,
            latency_ms=10,
            cost_usd=Decimal("0"),
            cost_source=CostSource.PROVIDER,
            started_at_utc=now,
            completed_at_utc=now,
            attempt_number=attempt_number,
        )


@pytest.mark.asyncio
async def test_pilot_persists_four_cells_and_resumes_without_duplicates(
    monkeypatch, registry, tmp_path
) -> None:
    data_dir = tmp_path / "data"
    benchmark_dir = data_dir / "benchmarks"
    benchmark_dir.mkdir(parents=True)
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "data"
        / "benchmarks"
        / "gsm8k_checkpoint1.jsonl"
    )
    (benchmark_dir / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    async def no_drift(_api_key: str | None = None) -> None:
        return None

    monkeypatch.setattr(registry, "validate_live_catalog", no_drift)
    adapter = FakeAdapter()
    runner = BenchmarkRunner(
        service=GenerationService(adapter),
        registry=registry,
        data_dir=data_dir,
        api_key="test-key",
        max_daily_requests=40,
        repository_root=tmp_path,
    )
    first = await runner.run(BenchmarkMode.PILOT)
    assert first.manifest.completed_cells == 4
    assert first.summary is not None
    assert all(model.accuracy == 1 for model in first.summary.models)
    assert adapter.calls == [
        registry.models[0].id,
        registry.models[1].id,
        registry.models[1].id,
        registry.models[0].id,
    ]

    await runner.run(BenchmarkMode.PILOT, first.manifest.run_id)
    assert len(adapter.calls) == 4
    records = runner.records(first.manifest.run_id, 0, 100)
    assert records.total == 4
