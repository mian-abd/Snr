from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app import __version__
from app.benchmarks.costs import PAID_DEMO_NAME, SPEND_CAP_USD, estimate_worst_case_usd
from app.benchmarks.gsm8k import load_samples
from app.domain.models import (
    BenchmarkEstimate,
    BenchmarkMode,
    BenchmarkRunView,
    BenchmarkStartRequest,
    ComparisonRequest,
    ComparisonResponse,
    EligibilityRequest,
    EligibilityResponse,
    EligibilityResult,
    GenerationRequest,
    HealthResponse,
    PaginatedRecords,
    RegistrySnapshot,
    RouteRequest,
    RouteResponse,
    RoutingDashboard,
    RoutingDecision,
    RoutingPool,
    RoutingValidationReport,
)
from app.registry.filtering import evaluate_eligibility
from app.registry.loader import ModelDriftError, ModelRegistry
from app.routing import RuleBasedRouter, build_dashboard, build_validation_report
from app.routing.replay import EVIDENCE_DIRS
from app.state import AppServices
from app.storage import append_jsonl

router = APIRouter(prefix="/api/v1")


def get_services(request: Request) -> AppServices:
    return cast(AppServices, request.app.state.services)


Services = Annotated[AppServices, Depends(get_services)]


def _require_live_services(services: AppServices) -> None:
    if not services.settings.credential_configured or services.generation_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A replacement OPENROUTER_API_KEY is not configured on the server",
        )


DEMO_DIRS = {RoutingPool.BASELINE: "checkpoint-1", RoutingPool.PAID: PAID_DEMO_NAME}


def _registry_for(services: AppServices, pool: RoutingPool) -> ModelRegistry:
    registry = services.pool_registry(pool)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The selected model pool is not configured",
        )
    return registry


async def _preflight(services: AppServices, registry: ModelRegistry) -> None:
    assert services.settings.openrouter_api_key is not None
    try:
        await registry.validate_live_catalog(
            services.settings.openrouter_api_key.get_secret_value()
        )
    except ModelDriftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenRouter catalog preflight failed: {type(exc).__name__}",
        ) from exc


@router.get("/health", response_model=HealthResponse)
async def health(services: Services) -> HealthResponse:
    active = next(
        (item.active_run_id for item in services.coordinators if item.active_run_id), None
    )
    return HealthResponse(
        status="ok",
        version=__version__,
        registry_loaded=True,
        registry_snapshot_id=services.registry.snapshot.snapshot_id,
        routing_registry_snapshot_id=(
            services.routing_registry.snapshot.snapshot_id if services.routing_registry else None
        ),
        credential_configured=services.settings.credential_configured,
        active_benchmark_run_id=active,
    )


@router.get("/models", response_model=RegistrySnapshot)
async def models(
    services: Services, pool: RoutingPool = RoutingPool.BASELINE
) -> RegistrySnapshot:
    return _registry_for(services, pool).snapshot


@router.get("/routing/models", response_model=RegistrySnapshot)
async def routing_models(services: Services) -> RegistrySnapshot:
    if services.routing_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The paid routing registry is not configured",
        )
    return services.routing_registry.snapshot


@router.post("/eligibility", response_model=EligibilityResponse)
async def eligibility(payload: EligibilityRequest, services: Services) -> EligibilityResponse:
    pools = [payload.pool] if payload.pool else [RoutingPool.BASELINE, RoutingPool.PAID]
    results: list[EligibilityResult] = []
    for pool in pools:
        registry = services.pool_registry(pool)
        if registry is None:
            continue
        results.extend(
            result.model_copy(update={"pool": pool})
            for result in evaluate_eligibility(registry.models, payload)
        )
    return EligibilityResponse(results=results)


@router.post("/comparisons", response_model=ComparisonResponse)
async def compare(payload: ComparisonRequest, services: Services) -> ComparisonResponse:
    _require_live_services(services)
    registry = _registry_for(services, payload.pool)
    generation_service = services.pool_generation_service(payload.pool)
    if generation_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The selected model pool is not configured",
        )
    await _preflight(services, registry)

    requests = [
        GenerationRequest(model_id=model.id, prompt=payload.prompt)
        for model in registry.models
    ]
    outcomes = await asyncio.gather(
        *(generation_service.generate_with_retries(item) for item in requests)
    )
    response = ComparisonResponse(
        prompt=payload.prompt,
        pool=payload.pool,
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


@router.post("/routes", response_model=RouteResponse)
async def route_prompt(payload: RouteRequest, services: Services) -> RouteResponse:
    """Select exactly one pinned model using the explicit CP2 rule policy."""
    _require_live_services(services)
    assert services.settings.openrouter_api_key is not None
    registry = (
        services.routing_registry
        if payload.pool == RoutingPool.PAID
        else services.registry
    )
    generation_service = (
        services.routing_generation_service
        if payload.pool == RoutingPool.PAID
        else services.generation_service
    )
    if registry is None or generation_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The selected routing pool is not configured",
        )
    try:
        await registry.validate_live_catalog(
            services.settings.openrouter_api_key.get_secret_value()
        )
        decision = RuleBasedRouter().decide(
            prompt=payload.prompt,
            priority=payload.priority,
            pool=payload.pool,
            models=registry.models,
            min_context_tokens=payload.min_context_tokens,
        )
    except ModelDriftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenRouter catalog preflight failed: {type(exc).__name__}",
        ) from exc

    outcome = await generation_service.generate_with_retries(
        GenerationRequest(model_id=decision.selected_model_id, prompt=payload.prompt)
    )
    return RouteResponse(
        decision=decision,
        result=outcome.final.model_copy(update={"provider_request_id": None}),
    )


@router.post("/routing/decisions", response_model=RoutingDecision)
async def preview_routing_decision(
    payload: RouteRequest, services: Services
) -> RoutingDecision:
    """Evaluate the fixed CP2 policy without a credential or provider request."""
    registry = (
        services.routing_registry
        if payload.pool == RoutingPool.PAID
        else services.registry
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The selected routing pool is not configured",
        )
    try:
        return RuleBasedRouter().decide(
            prompt=payload.prompt,
            priority=payload.priority,
            pool=payload.pool,
            models=registry.models,
            min_context_tokens=payload.min_context_tokens,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/routing/dashboard", response_model=RoutingDashboard)
async def routing_dashboard(
    services: Services, pool: RoutingPool = RoutingPool.BASELINE
) -> RoutingDashboard:
    """Replay fixed and rule strategies over one saved evidence matrix."""
    try:
        return build_dashboard(
            services.settings.data_dir / "demo" / EVIDENCE_DIRS[pool], pool=pool
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/routing/validation", response_model=RoutingValidationReport)
async def routing_validation(
    services: Services, pool: RoutingPool = RoutingPool.BASELINE
) -> RoutingValidationReport:
    """Run the fixed CP2 policy acceptance matrix without provider calls."""
    registry = services.routing_registry if pool == RoutingPool.PAID else services.registry
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The selected routing pool is not configured",
        )
    return build_validation_report(registry.models, pool=pool)


def _estimate(
    services: AppServices, pool: RoutingPool, mode: BenchmarkMode
) -> BenchmarkEstimate:
    registry = _registry_for(services, pool)
    samples = load_samples(services.settings.data_dir / "benchmarks" / "gsm8k_checkpoint1.jsonl")
    if mode == BenchmarkMode.PILOT:
        samples = samples[:2]
    worst_case = estimate_worst_case_usd(registry.models, samples)
    paid = pool == RoutingPool.PAID
    return BenchmarkEstimate(
        pool=pool,
        mode=mode,
        model_ids=[model.id for model in registry.models],
        samples=len(samples),
        cells=len(samples) * len(registry.models),
        worst_case_usd=worst_case,
        spend_cap_usd=SPEND_CAP_USD if paid else None,
        within_cap=not paid or worst_case <= SPEND_CAP_USD,
        requires_confirmation=paid,
    )


@router.get("/benchmarks/gsm8k/estimate", response_model=BenchmarkEstimate)
async def benchmark_estimate(
    services: Services,
    pool: RoutingPool = RoutingPool.BASELINE,
    mode: BenchmarkMode = BenchmarkMode.FULL,
) -> BenchmarkEstimate:
    """Worst-case cost of a run before anything is spent (no provider call)."""
    return _estimate(services, pool, mode)


@router.post(
    "/benchmarks/gsm8k/runs",
    response_model=BenchmarkRunView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_benchmark(
    payload: BenchmarkStartRequest, services: Services
) -> BenchmarkRunView:
    _require_live_services(services)
    coordinator = services.pool_benchmark_coordinator(payload.pool)
    runner = services.pool_benchmark_runner(payload.pool)
    if coordinator is None or runner is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The selected model pool has no benchmark runner",
        )
    if any(item.is_running for item in services.coordinators):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A benchmark is already running"
        )
    estimate = _estimate(services, payload.pool, payload.mode)
    if estimate.requires_confirmation:
        if not estimate.within_cap:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Estimated ${estimate.worst_case_usd:.4f} exceeds the "
                    f"${estimate.spend_cap_usd} spending cap"
                ),
            )
        if payload.confirmed_estimate_usd is None or (
            payload.confirmed_estimate_usd.quantize(Decimal("0.0001"))
            != estimate.worst_case_usd.quantize(Decimal("0.0001"))
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirm the current cost estimate before starting a paid run",
            )
    registry = _registry_for(services, payload.pool)
    await _preflight(services, registry)
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

        manifest = BenchmarkManifest(
            run_id=run_id,
            mode=payload.mode,
            status=BenchmarkStatus.PENDING,
            dataset="openai/gsm8k",
            dataset_revision="b0bb162abedc65e1fdd8e93ed090fd7598ee68bc",
            registry_snapshot_id=registry.snapshot.snapshot_id,
            registry_models_sha256=registry.snapshot.models_sha256,
            model_ids=[model.id for model in registry.models],
            generation_config=GENERATION_CONFIG,
            generation_config_hash=_config_hash(),
            git_commit=None,
            total_cells=estimate.cells,
            created_at_utc=datetime.now(UTC),
            updated_at_utc=datetime.now(UTC),
        )
        return BenchmarkRunView(manifest=manifest)


@router.get("/benchmarks/runs/latest", response_model=BenchmarkRunView)
async def latest_benchmark(
    services: Services, pool: RoutingPool = RoutingPool.BASELINE
) -> BenchmarkRunView:
    runner = services.pool_benchmark_runner(pool)
    result = runner.latest_run() if runner else None
    if result is None:
        # Committed evidence remains readable without a credential or a local run.
        demo = services.settings.data_dir / "demo" / DEMO_DIRS[pool]
        if not (demo / "manifest.json").exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No benchmark run found"
            )
        return _load_demo(demo)
    return result


@router.get("/benchmarks/runs/{run_id}", response_model=BenchmarkRunView)
async def benchmark_run(run_id: str, services: Services) -> BenchmarkRunView:
    for pool in RoutingPool:
        runner = services.pool_benchmark_runner(pool)
        if runner:
            try:
                return runner.load_run(run_id)
            except FileNotFoundError:
                pass
        demo = services.settings.data_dir / "demo" / DEMO_DIRS[pool]
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
    from app.domain.models import BenchmarkRecord
    from app.storage import read_jsonl

    for pool in RoutingPool:
        runner = services.pool_benchmark_runner(pool)
        if runner:
            try:
                return runner.records(run_id, offset, limit)
            except FileNotFoundError:
                pass
        demo = services.settings.data_dir / "demo" / DEMO_DIRS[pool]
        rows = [
            BenchmarkRecord.model_validate(row) for row in read_jsonl(demo / "results.jsonl")
        ]
        if rows and rows[0].run_id == run_id:
            return PaginatedRecords(
                items=rows[offset : offset + limit], total=len(rows), offset=offset, limit=limit
            )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark run not found")


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
