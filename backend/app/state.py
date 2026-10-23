from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.benchmarks.costs import (
    PAID_BUDGET_FILE,
    PAID_DEMO_NAME,
    PAID_MAX_REQUESTS,
    PAID_RUN_PREFIX,
)
from app.benchmarks.runner import BenchmarkRunner
from app.config import REPOSITORY_ROOT, Settings
from app.domain.models import BenchmarkMode, BenchmarkStatus, RoutingPool
from app.providers import GenerationService
from app.registry import ModelRegistry

REGISTRY_PATH = REPOSITORY_ROOT / "data" / "registry" / "openrouter-2026-09-30.json"
PAID_REGISTRY_PATH = REPOSITORY_ROOT / "data" / "registry" / "openrouter-paid-2026-10-23.json"
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


def build_services(settings: Settings) -> AppServices:
    registry = ModelRegistry(REGISTRY_PATH)
    routing_registry = ModelRegistry(
        PAID_REGISTRY_PATH,
        expected_model_ids=PAID_MODEL_IDS,
        require_free=False,
    )
    if not settings.credential_configured:
        return AppServices(
            settings=settings,
            registry=registry,
            generation_service=None,
            benchmark_runner=None,
            routing_registry=routing_registry,
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
    )
