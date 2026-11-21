from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.benchmarks.costs import (
    PAID_BUDGET_FILE,
    PAID_DEMO_NAME,
    PAID_MAX_REQUESTS,
    PAID_RUN_PREFIX,
)
from app.benchmarks.runner import BenchmarkRunner
from app.config import REPOSITORY_ROOT, Settings
from app.domain.models import (
    BenchmarkMode,
    BenchmarkStatus,
    LearnedPool,
    LiveCatalogStatus,
    RoutingPool,
)
from app.learned.router import ROUTER_MODEL_FILE, ROUTER_POOL_FILE, LearnedRouter, load_router
from app.learned.studies import POOL_STUDY, STUDIES
from app.providers import GenerationService
from app.providers.openai_compatible import OpenAICompatibleAdapter
from app.registry import ModelRegistry
from app.registry.live_catalog import check_live_catalog, snapshot_status
from app.registry.pool import combine_pools, endpoint_for, load_pool

REGISTRY_PATH = REPOSITORY_ROOT / "data" / "registry" / "openrouter-2026-09-30.json"
PAID_REGISTRY_PATH = REPOSITORY_ROOT / "data" / "registry" / "openrouter-paid-2026-10-23.json"
CATALOG_TIMEOUT_SECONDS = 12.0  # startup waits at most this long, then uses the snapshot
PAID_MODEL_IDS = (
    "google/gemma-4-26b-a4b-it",
    "inception/mercury-3",
    "google/gemini-4-argon",
)


@dataclass
class AppServices:
    settings: Settings
    registry: ModelRegistry
    generation_service: GenerationService | None
    benchmark_runner: BenchmarkRunner | None
    benchmark_coordinator: BenchmarkCoordinator | None = None
    routing_registry: ModelRegistry | None = None
    routing_generation_service: GenerationService | None = None
    paid_benchmark_runner: BenchmarkRunner | None = None
    paid_benchmark_coordinator: BenchmarkCoordinator | None = None
    learned_router: LearnedRouter | None = None
    learned_generation_service: GenerationService | None = None
    # Pool studies' routers, by study ID ("flagship", "wide"), and clients for their pools.
    study_routers: dict[str, LearnedRouter] = field(default_factory=dict)
    study_generation_services: dict[str, GenerationService] = field(default_factory=dict)
    catalog: LiveCatalogStatus | None = None
    catalog_transport: httpx.AsyncBaseTransport | None = None  # tests inject a mock

    async def refresh_catalog(self) -> LiveCatalogStatus | None:
        """Check the learned router's pool against the live catalogs; never raises."""
        router = self.learned_router
        if router is None:
            return None
        snapshot = router.pool
        if not self.settings.live_catalog_check:
            self.catalog = snapshot_status(snapshot)
            return self.catalog
        # The studies' added models are checked too, so every pool sees the same catalog.
        models = dict(router.models)
        for other in self.study_routers.values():
            for model_id, model in other.models.items():
                models.setdefault(model_id, model)
        try:
            self.catalog = await asyncio.wait_for(
                check_live_catalog(
                    models.values(), snapshot, transport=self.catalog_transport
                ),
                timeout=CATALOG_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # the snapshot is always a safe fallback
            self.catalog = snapshot_status(
                snapshot, error=f"Live catalog check failed ({type(exc).__name__})"
            )
        return self.catalog

    def router_for(self, pool: LearnedPool) -> LearnedRouter | None:
        if pool == LearnedPool.STANDARD:
            return self.learned_router
        return self.study_routers.get(POOL_STUDY[pool.value])

    def generation_for(self, pool: LearnedPool) -> GenerationService | None:
        if pool == LearnedPool.STANDARD:
            return self.learned_generation_service
        return self.study_generation_services.get(POOL_STUDY[pool.value])

    def pool_registry(self, pool: RoutingPool) -> ModelRegistry | None:
        return self.routing_registry if pool == RoutingPool.PAID else self.registry

    def pool_generation_service(self, pool: RoutingPool) -> GenerationService | None:
        return (
            self.routing_generation_service
            if pool == RoutingPool.PAID
            else self.generation_service
        )

    def pool_benchmark_runner(self, pool: RoutingPool) -> BenchmarkRunner | None:
        return self.paid_benchmark_runner if pool == RoutingPool.PAID else self.benchmark_runner

    def pool_benchmark_coordinator(self, pool: RoutingPool) -> BenchmarkCoordinator | None:
        return (
            self.paid_benchmark_coordinator
            if pool == RoutingPool.PAID
            else self.benchmark_coordinator
        )

    @property
    def coordinators(self) -> list[BenchmarkCoordinator]:
        return [
            item
            for item in (self.benchmark_coordinator, self.paid_benchmark_coordinator)
            if item is not None
        ]


class BenchmarkCoordinator:
    def __init__(self, runner: BenchmarkRunner) -> None:
        self.runner = runner
        self.active_run_id: str | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, mode: BenchmarkMode) -> str:
        if self.is_running:
            raise RuntimeError("A benchmark is already running")
        latest = self.runner.latest_run()
        resumable = {
            BenchmarkStatus.BUDGET_PAUSED,
            BenchmarkStatus.INTERRUPTED,
            BenchmarkStatus.RUNNING,
        }
        if latest and latest.manifest.mode == mode and latest.manifest.status in resumable:
            run_id = latest.manifest.run_id
        else:
            run_id = self.runner.new_run_id(mode)
        self.active_run_id = run_id
        self._task = asyncio.create_task(self._execute(mode, run_id), name=f"benchmark:{run_id}")
        return run_id

    async def _execute(self, mode: BenchmarkMode, run_id: str) -> None:
        try:
            await self.runner.run(mode, run_id)
        finally:
            self.active_run_id = None


def build_learned_services(
    settings: Settings,
) -> tuple[LearnedRouter | None, GenerationService | None]:
    """The exported learned router and a client for its pool, or neither before training."""
    artifact = settings.data_dir / ROUTER_MODEL_FILE
    if not artifact.exists():
        return None, None
    router = load_router(artifact, load_pool(settings.data_dir / ROUTER_POOL_FILE))
    keys = (
        {"OPENROUTER_API_KEY": settings.openrouter_api_key.get_secret_value()}
        if settings.openrouter_api_key and settings.credential_configured
        else {}
    )
    adapter = OpenAICompatibleAdapter(
        [endpoint_for(model) for model in router.models.values()], keys=keys
    )
    return router, GenerationService(adapter)


def build_study_services(
    settings: Settings, study_id: str
) -> tuple[LearnedRouter | None, GenerationService | None]:
    """A pool study's router and a client for its pool, if that study has been fit."""
    spec = STUDIES[study_id]
    artifact = settings.data_dir / "learned" / spec.router_path.name
    if not artifact.exists():
        return None, None
    try:
        pool = combine_pools(
            load_pool(settings.data_dir / ROUTER_POOL_FILE),
            *(load_pool(settings.data_dir / "registry" / added.registry_file)
              for added in spec.added),
        )
        router = load_router(artifact, pool)
    except (OSError, ValueError) as exc:
        # Study routers are optional: a broken file must not take the standard one down.
        logging.getLogger(__name__).warning("%s router not loaded: %s", study_id, exc)
        return None, None
    keys = (
        {"OPENROUTER_API_KEY": settings.openrouter_api_key.get_secret_value()}
        if settings.openrouter_api_key and settings.credential_configured
        else {}
    )
    adapter = OpenAICompatibleAdapter(
        [endpoint_for(model) for model in router.models.values()], keys=keys
    )
    return router, GenerationService(adapter)


def build_services(settings: Settings) -> AppServices:
    registry = ModelRegistry(REGISTRY_PATH)
    routing_registry = ModelRegistry(
        PAID_REGISTRY_PATH,
        expected_model_ids=PAID_MODEL_IDS,
        require_free=False,
    )
    learned_router, learned_service = build_learned_services(settings)
    studies = {study_id: build_study_services(settings, study_id) for study_id in STUDIES}
    study_routers = {key: router for key, (router, _) in studies.items() if router is not None}
    study_services = {key: service for key, (_, service) in studies.items() if service is not None}
    if not settings.credential_configured:
        return AppServices(
            settings=settings,
            registry=registry,
            generation_service=None,
            benchmark_runner=None,
            routing_registry=routing_registry,
            learned_router=learned_router,
            learned_generation_service=learned_service,
            study_routers=study_routers,
            study_generation_services=study_services,
        )
    assert settings.openrouter_api_key is not None
    from app.providers.litellm_openrouter import LiteLLMOpenRouterAdapter

    api_key = settings.openrouter_api_key.get_secret_value()
    adapter = LiteLLMOpenRouterAdapter(
        api_key=api_key,
        registry=registry,
        site_url=settings.openrouter_site_url,
        app_name=settings.openrouter_app_name,
    )
    service = GenerationService(adapter)
    routing_adapter = LiteLLMOpenRouterAdapter(
        api_key=api_key,
        registry=routing_registry,
        site_url=settings.openrouter_site_url,
        app_name=settings.openrouter_app_name,
    )
    routing_service = GenerationService(routing_adapter)
    runner = BenchmarkRunner(
        service=service,
        registry=registry,
        data_dir=settings.data_dir,
        api_key=api_key,
        max_daily_requests=settings.max_daily_provider_requests,
        repository_root=Path(REPOSITORY_ROOT),
    )
    coordinator = BenchmarkCoordinator(runner)
    paid_runner = BenchmarkRunner(
        service=routing_service,
        registry=routing_registry,
        data_dir=settings.data_dir,
        api_key=api_key,
        max_daily_requests=PAID_MAX_REQUESTS,
        repository_root=Path(REPOSITORY_ROOT),
        demo_name=PAID_DEMO_NAME,
        run_prefix=PAID_RUN_PREFIX,
        budget_file=PAID_BUDGET_FILE,
    )
    return AppServices(
        settings=settings,
        registry=registry,
        generation_service=service,
        benchmark_runner=runner,
        benchmark_coordinator=coordinator,
        routing_registry=routing_registry,
        routing_generation_service=routing_service,
        paid_benchmark_runner=paid_runner,
        paid_benchmark_coordinator=BenchmarkCoordinator(paid_runner),
        learned_router=learned_router,
        learned_generation_service=learned_service,
        study_routers=study_routers,
        study_generation_services=study_services,
    )
