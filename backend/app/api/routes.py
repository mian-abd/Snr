from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app import __version__
from app.domain.models import (
    BenchmarkRunView,
    BenchmarkStartRequest,
    ComparisonRequest,
    ComparisonResponse,
    EligibilityRequest,
    EligibilityResponse,
    GenerationRequest,
    HealthResponse,
    PaginatedRecords,
    RegistrySnapshot,
)
from app.registry.filtering import evaluate_eligibility
from app.registry.loader import ModelDriftError
from app.state import AppServices
from app.storage import append_jsonl

router = APIRouter(prefix="/api/v1")


def get_services(request: Request) -> AppServices:
    return request.app.state.services


Services = Annotated[AppServices, Depends(get_services)]


def _require_live_services(services: AppServices) -> None:
    if not services.settings.credential_configured or services.generation_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A replacement OPENROUTER_API_KEY is not configured on the server",
        )


@router.get("/health", response_model=HealthResponse)
async def health(services: Services) -> HealthResponse:
    coordinator = services.benchmark_coordinator
    return HealthResponse(
        status="ok",
        version=__version__,
        registry_loaded=True,
        registry_snapshot_id=services.registry.snapshot.snapshot_id,
        credential_configured=services.settings.credential_configured,
        active_benchmark_run_id=coordinator.active_run_id if coordinator else None,
    )


@router.get("/models", response_model=RegistrySnapshot)
async def models(services: Services) -> RegistrySnapshot:
    return services.registry.snapshot


@router.post("/eligibility", response_model=EligibilityResponse)
async def eligibility(payload: EligibilityRequest, services: Services) -> EligibilityResponse:
    return EligibilityResponse(
        results=evaluate_eligibility(services.registry.models, payload)
    )


@router.post("/comparisons", response_model=ComparisonResponse)
async def compare(payload: ComparisonRequest, services: Services) -> ComparisonResponse:
    _require_live_services(services)
    assert services.settings.openrouter_api_key is not None
    assert services.generation_service is not None
    try:
        await services.registry.validate_live_catalog(
            services.settings.openrouter_api_key.get_secret_value()
        )
    except ModelDriftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenRouter catalog preflight failed: {type(exc).__name__}",
        ) from exc

    requests = [
        GenerationRequest(model_id=model.id, prompt=payload.prompt)
        for model in services.registry.models
    ]
    outcomes = await asyncio.gather(
        *(services.generation_service.generate_with_retries(item) for item in requests)
    )
    response = ComparisonResponse(
        prompt=payload.prompt,
        saved=payload.save,
        results=[
            outcome.final.model_copy(update={"provider_request_id": None})
            for outcome in outcomes
        ],
    )
    if payload.save:
        append_jsonl(
            services.settings.data_dir / "local" / "manual" / "comparisons.jsonl",
            response,
        )
    return response


@router.post(
    "/benchmarks/gsm8k/runs",
    response_model=BenchmarkRunView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_benchmark(
    payload: BenchmarkStartRequest, services: Services
) -> BenchmarkRunView:
    _require_live_services(services)
    coordinator = services.benchmark_coordinator
    runner = services.benchmark_runner
    assert coordinator is not None and runner is not None
    assert services.settings.openrouter_api_key is not None
    try:
        await services.registry.validate_live_catalog(
            services.settings.openrouter_api_key.get_secret_value()
        )
    except ModelDriftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenRouter catalog preflight failed: {type(exc).__name__}",
        ) from exc
    try:
        run_id = coordinator.start(payload.mode)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        return runner.load_run(run_id)
    except FileNotFoundError:
        from datetime import UTC, datetime

        from app.benchmarks.runner import GENERATION_CONFIG, _config_hash
        from app.domain.models import BenchmarkManifest, BenchmarkStatus

        samples_count = 2 if payload.mode.value == "pilot" else 12
        manifest = BenchmarkManifest(
            run_id=run_id,
            mode=payload.mode,
            status=BenchmarkStatus.PENDING,
            dataset="openai/gsm8k",
            dataset_revision="b0bb162abedc65e1fdd8e93ed090fd7598ee68bc",
            registry_snapshot_id=services.registry.snapshot.snapshot_id,
            registry_models_sha256=services.registry.snapshot.models_sha256,
            model_ids=[model.id for model in services.registry.models],
            generation_config=GENERATION_CONFIG,
            generation_config_hash=_config_hash(),
            git_commit=None,
            total_cells=samples_count * 2,
            created_at_utc=datetime.now(UTC),
            updated_at_utc=datetime.now(UTC),
        )
        return BenchmarkRunView(manifest=manifest)


@router.get("/benchmarks/runs/latest", response_model=BenchmarkRunView)
async def latest_benchmark(services: Services) -> BenchmarkRunView:
    runner = services.benchmark_runner
    if runner is None:
        # A committed demo remains readable without a credential.
        demo = services.settings.data_dir / "demo" / "checkpoint-1"
        if not (demo / "manifest.json").exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No benchmark run found"
            )
        return _load_demo(demo)
    result = runner.latest_run()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No benchmark run found")
    return result


@router.get("/benchmarks/runs/{run_id}", response_model=BenchmarkRunView)
async def benchmark_run(run_id: str, services: Services) -> BenchmarkRunView:
    if services.benchmark_runner:
        try:
            return services.benchmark_runner.load_run(run_id)
        except FileNotFoundError:
            pass
    demo = services.settings.data_dir / "demo" / "checkpoint-1"
    if (demo / "manifest.json").exists():
        view = _load_demo(demo)
        if view.manifest.run_id == run_id:
            return view
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark run not found")


@router.get("/benchmarks/runs/{run_id}/records", response_model=PaginatedRecords)
async def benchmark_records(
    run_id: str,
    services: Services,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PaginatedRecords:
    if services.benchmark_runner:
        try:
            return services.benchmark_runner.records(run_id, offset, limit)
        except FileNotFoundError:
            pass
    demo = services.settings.data_dir / "demo" / "checkpoint-1"
    from app.domain.models import BenchmarkRecord
    from app.storage import read_jsonl

    rows = [BenchmarkRecord.model_validate(row) for row in read_jsonl(demo / "results.jsonl")]
    if not rows or rows[0].run_id != run_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark run not found")
    return PaginatedRecords(
        items=rows[offset : offset + limit], total=len(rows), offset=offset, limit=limit
    )


def _load_demo(path: Path) -> BenchmarkRunView:
    from app.domain.models import BenchmarkManifest, BenchmarkSummary

    manifest = BenchmarkManifest.model_validate_json(
        (path / "manifest.json").read_text(encoding="utf-8")
    )
    summary_path = path / "summary.json"
    summary = (
        BenchmarkSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists()
        else None
    )
    return BenchmarkRunView(manifest=manifest, summary=summary)
