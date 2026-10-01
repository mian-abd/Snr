from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.benchmarks.runner import BenchmarkRunner
from app.config import REPOSITORY_ROOT, Settings
from app.domain.models import BenchmarkMode, BenchmarkStatus
from app.providers import GenerationService
from app.registry import ModelRegistry

REGISTRY_PATH = REPOSITORY_ROOT / "data" / "registry" / "openrouter-2026-09-30.json"


@dataclass
class AppServices:
    settings: Settings
    registry: ModelRegistry
    generation_service: GenerationService | None
    benchmark_runner: BenchmarkRunner | None
    benchmark_coordinator: BenchmarkCoordinator | None = None


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
    if not settings.credential_configured:
        return AppServices(
            settings=settings,
            registry=registry,
            generation_service=None,
            benchmark_runner=None,
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
    runner = BenchmarkRunner(
        service=service,
        registry=registry,
        data_dir=settings.data_dir,
        api_key=api_key,
        max_daily_requests=settings.max_daily_provider_requests,
        repository_root=Path(REPOSITORY_ROOT),
    )
    coordinator = BenchmarkCoordinator(runner)
    return AppServices(
        settings=settings,
        registry=registry,
        generation_service=service,
        benchmark_runner=runner,
        benchmark_coordinator=coordinator,
    )
