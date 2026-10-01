from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from filelock import FileLock, Timeout

from app.benchmarks.gsm8k import (
    PROMPT_TEMPLATE_VERSION,
    SYSTEM_PROMPT,
    exact_match,
    extract_answer,
    load_samples,
    render_prompt,
)
from app.domain.models import (
    BenchmarkManifest,
    BenchmarkMode,
    BenchmarkRecord,
    BenchmarkRunView,
    BenchmarkStatus,
    BenchmarkSummary,
    ExperimentContext,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    ModelBenchmarkSummary,
    PaginatedRecords,
)
from app.providers.service import GenerationService
from app.registry.loader import ModelRegistry
from app.storage import (
    append_jsonl,
    atomic_write_json,
    atomic_write_jsonl,
    read_jsonl,
    sanitize_text,
)

GENERATION_CONFIG: dict[str, Any] = {
    "temperature": 0,
    "max_tokens": 512,
    "timeout_seconds": 90,
    "stream": False,
    "prompt_template_version": PROMPT_TEMPLATE_VERSION,
}


def _config_hash() -> str:
    encoded = json.dumps(GENERATION_CONFIG, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _git_commit(repository_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


class RequestBudget:
    def __init__(self, path: Path, maximum: int) -> None:
        self.path = path
        self.maximum = maximum

    def _state(self) -> dict[str, Any]:
        today = date.today().isoformat()
        if not self.path.exists():
            return {"date": today, "count": 0}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return {"date": today, "count": 0}
        if state.get("date") != today:
            return {"date": today, "count": 0}
        return {str(key): value for key, value in state.items()}

    @property
    def remaining(self) -> int:
        return max(0, self.maximum - int(self._state().get("count", 0)))

    def increment(self) -> None:
        state = self._state()
        state["count"] = int(state.get("count", 0)) + 1
        atomic_write_json(self.path, state)


class BenchmarkRunner:
    def __init__(
        self,
        *,
        service: GenerationService,
        registry: ModelRegistry,
        data_dir: Path,
        api_key: str,
        max_daily_requests: int,
        repository_root: Path,
    ) -> None:
        self.service = service
        self.registry = registry
        self.data_dir = data_dir
        self.api_key = api_key
        self.repository_root = repository_root
        self.samples_path = data_dir / "benchmarks" / "gsm8k_checkpoint1.jsonl"
        self.runs_dir = data_dir / "local" / "runs"
        self.demo_dir = data_dir / "demo" / "checkpoint-1"
        self.lock_path = data_dir / "local" / "benchmark.lock"
        self.budget = RequestBudget(
            data_dir / "local" / "provider-request-budget.json", max_daily_requests
        )

    async def run(self, mode: BenchmarkMode, run_id: str | None = None) -> BenchmarkRunView:
        lock = FileLock(self.lock_path, timeout=0)
        try:
            lock.acquire()
        except Timeout as exc:
            raise RuntimeError("Another benchmark process is already active") from exc
        try:
            await self.registry.validate_live_catalog(self.api_key)
            samples = load_samples(self.samples_path)
            if mode == BenchmarkMode.PILOT:
                samples = samples[:2]
            run_id = run_id or self.new_run_id(mode)
            run_dir = self.runs_dir / run_id
            manifest_path = run_dir / "manifest.json"
            attempts_path = run_dir / "attempts.jsonl"
            results_path = run_dir / "results.jsonl"
            summary_path = run_dir / "summary.json"
            manifest = self._load_or_create_manifest(manifest_path, run_id, mode, samples)
            manifest.status = BenchmarkStatus.RUNNING
            manifest.error_message = None
            manifest.updated_at_utc = datetime.now(UTC)
            atomic_write_json(manifest_path, manifest)

            attempts = read_jsonl(attempts_path)
            records = [BenchmarkRecord.model_validate(row) for row in read_jsonl(results_path)]
            complete_keys = {(row.sample_id, row.result.requested_model_id) for row in records}

            for sample_position, sample in enumerate(samples):
                model_ids = list(self.registry.snapshot.models)
                if sample_position % 2:
                    model_ids.reverse()
                for model in model_ids:
                    cell_key = (sample.sample_id, model.id)
                    if cell_key in complete_keys:
                        continue
                    previous = [
                        GenerationResult.model_validate(item["result"])
                        for item in attempts
                        if item["sample_id"] == sample.sample_id and item["model_id"] == model.id
                    ]
                    if len(previous) >= 2:
                        final = previous[-1]
                    else:
                        if self.budget.remaining <= 0:
                            manifest.status = BenchmarkStatus.BUDGET_PAUSED
                            manifest.updated_at_utc = datetime.now(UTC)
                            atomic_write_json(manifest_path, manifest)
                            return self._view(manifest, records)
                        request_id = previous[0].request_id if previous else uuid4()
                        request = GenerationRequest(
                            request_id=request_id,
                            model_id=model.id,
                            prompt=render_prompt(sample.question),
                            system_prompt=SYSTEM_PROMPT,
                            experiment_context=ExperimentContext(
                                run_id=run_id, sample_id=sample.sample_id
                            ),
                        )

                        async def save_attempt(
                            result: GenerationResult,
                            sample_id: str = sample.sample_id,
                            model_id: str = model.id,
                        ) -> None:
                            envelope = {
                                "run_id": run_id,
                                "sample_id": sample_id,
                                "model_id": model_id,
                                "result": result.model_dump(mode="json"),
                            }
                            append_jsonl(attempts_path, envelope)
                            attempts.append(envelope)
                            self.budget.increment()

                        allowed_attempts = min(2, len(previous) + self.budget.remaining)
                        outcome = await self.service.generate_with_retries(
                            request,
                            start_attempt=len(previous) + 1,
                            max_attempts=allowed_attempts,
                            on_attempt=save_attempt,
                        )
                        final = outcome.final
                        if (
                            self.service.is_retryable(final)
                            and final.attempt_number < 2
                            and self.budget.remaining <= 0
                        ):
                            manifest.status = BenchmarkStatus.BUDGET_PAUSED
                            manifest.updated_at_utc = datetime.now(UTC)
                            atomic_write_json(manifest_path, manifest)
                            return self._view(manifest, records)

                    extracted, method = extract_answer(final.text)
                    score = (
                        exact_match(extracted, sample.expected_answer)
                        if final.status == GenerationStatus.SUCCESS
                        else 0
                    )
                    record = BenchmarkRecord(
                        run_id=run_id,
                        mode=mode,
                        dataset=sample.dataset,
                        configuration=sample.configuration,
                        revision=sample.revision,
                        split=sample.split,
                        source_index=sample.source_index,
                        sample_id=sample.sample_id,
                        prompt_template_version=PROMPT_TEMPLATE_VERSION,
                        rendered_prompt=render_prompt(sample.question),
                        expected_answer=sample.expected_answer,
                        extracted_answer=extracted,
                        extraction_method=method,
                        exact_match=score,
                        result=final,
                        model_snapshot_id=self.registry.snapshot.snapshot_id,
                        generation_config_hash=_config_hash(),
                    )
                    records.append(record)
                    complete_keys.add(cell_key)
                    atomic_write_jsonl(results_path, records)
                    self._update_counts(manifest, records)
                    manifest.updated_at_utc = datetime.now(UTC)
                    atomic_write_json(manifest_path, manifest)
                    atomic_write_json(summary_path, self._summarize(run_id, records))

            self._update_counts(manifest, records)
            manifest.status = (
                BenchmarkStatus.COMPLETED_WITH_ERRORS
                if manifest.failed_cells
                else BenchmarkStatus.COMPLETED
            )
            manifest.updated_at_utc = datetime.now(UTC)
            summary = self._summarize(run_id, records)
            atomic_write_json(manifest_path, manifest)
            atomic_write_json(summary_path, summary)
            return BenchmarkRunView(manifest=manifest, summary=summary)
        except Exception as exc:
            if "manifest" in locals() and "manifest_path" in locals():
                manifest.status = BenchmarkStatus.FAILED
                manifest.error_message = str(exc)[:1000]
                manifest.updated_at_utc = datetime.now(UTC)
                atomic_write_json(manifest_path, manifest)
            raise
        finally:
            lock.release()

    def new_run_id(self, mode: BenchmarkMode) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"gsm8k-{mode.value}-{stamp}-{uuid4().hex[:8]}"

    def _load_or_create_manifest(
        self, path: Path, run_id: str, mode: BenchmarkMode, samples: list[Any]
    ) -> BenchmarkManifest:
        if path.exists():
            existing = BenchmarkManifest.model_validate_json(path.read_text(encoding="utf-8"))
            if existing.mode != mode:
                raise ValueError("Cannot resume a run using a different mode")
            return existing
        now = datetime.now(UTC)
        return BenchmarkManifest(
            run_id=run_id,
            mode=mode,
            status=BenchmarkStatus.PENDING,
            dataset=samples[0].dataset,
            dataset_revision=samples[0].revision,
            registry_snapshot_id=self.registry.snapshot.snapshot_id,
            registry_models_sha256=self.registry.snapshot.models_sha256,
            model_ids=[model.id for model in self.registry.models],
            generation_config=GENERATION_CONFIG,
            generation_config_hash=_config_hash(),
            git_commit=_git_commit(self.repository_root),
            total_cells=len(samples) * len(self.registry.models),
            created_at_utc=now,
            updated_at_utc=now,
        )

    @staticmethod
    def _update_counts(manifest: BenchmarkManifest, records: list[BenchmarkRecord]) -> None:
        manifest.completed_cells = len(records)
        manifest.successful_cells = sum(
            record.result.status == GenerationStatus.SUCCESS for record in records
        )
        manifest.failed_cells = manifest.completed_cells - manifest.successful_cells

    def _summarize(self, run_id: str, records: list[BenchmarkRecord]) -> BenchmarkSummary:
        model_summaries: list[ModelBenchmarkSummary] = []
        for model_id in [model.id for model in self.registry.models]:
            rows = [row for row in records if row.result.requested_model_id == model_id]
            successful = [row for row in rows if row.result.status == GenerationStatus.SUCCESS]
            latencies = [row.result.latency_ms for row in successful]
            costs = [row.result.cost_usd for row in rows if row.result.cost_usd is not None]
            errors = Counter(
                row.result.status.value
                for row in rows
                if row.result.status != GenerationStatus.SUCCESS
            )
            model_summaries.append(
                ModelBenchmarkSummary(
                    model_id=model_id,
                    attempted=len(rows),
                    successful=len(successful),
                    failed=len(rows) - len(successful),
                    correct=sum(row.exact_match for row in rows),
                    accuracy=(sum(row.exact_match for row in rows) / len(rows) if rows else 0),
                    mean_latency_ms=statistics.mean(latencies) if latencies else None,
                    median_latency_ms=statistics.median(latencies) if latencies else None,
                    prompt_tokens=sum(row.result.prompt_tokens or 0 for row in rows),
                    completion_tokens=sum(row.result.completion_tokens or 0 for row in rows),
                    total_tokens=sum(row.result.total_tokens or 0 for row in rows),
                    total_cost_usd=sum(costs, Decimal("0")) if costs else None,
                    error_counts=dict(errors),
                )
            )
        return BenchmarkSummary(
            run_id=run_id, generated_at_utc=datetime.now(UTC), models=model_summaries
        )

    def _view(
        self, manifest: BenchmarkManifest, records: list[BenchmarkRecord]
    ) -> BenchmarkRunView:
        return BenchmarkRunView(
            manifest=manifest,
            summary=self._summarize(manifest.run_id, records) if records else None,
        )

    def load_run(self, run_id: str) -> BenchmarkRunView:
        run_dir = self._resolve_run_dir(run_id)
        manifest = BenchmarkManifest.model_validate_json(
            (run_dir / "manifest.json").read_text(encoding="utf-8")
        )
        summary_path = run_dir / "summary.json"
        summary = (
            BenchmarkSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
            if summary_path.exists()
            else None
        )
        return BenchmarkRunView(manifest=manifest, summary=summary)

    def latest_run(self) -> BenchmarkRunView | None:
        candidates = list(self.runs_dir.glob("*/manifest.json")) if self.runs_dir.exists() else []
        demo_manifest = self.demo_dir / "manifest.json"
        if demo_manifest.exists():
            candidates.append(demo_manifest)
        if not candidates:
            return None
        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        manifest = BenchmarkManifest.model_validate_json(latest.read_text(encoding="utf-8"))
        return self.load_run(manifest.run_id)

    def records(self, run_id: str, offset: int, limit: int) -> PaginatedRecords:
        rows = [
            BenchmarkRecord.model_validate(row)
            for row in read_jsonl(self._resolve_run_dir(run_id) / "results.jsonl")
        ]
        return PaginatedRecords(
            items=rows[offset : offset + limit], total=len(rows), offset=offset, limit=limit
        )

    def sanitize_run(self, run_id: str) -> Path:
        source = self._resolve_run_dir(run_id)
        destination = self.demo_dir
        manifest = BenchmarkManifest.model_validate_json(
            (source / "manifest.json").read_text(encoding="utf-8")
        )
        records = [
            BenchmarkRecord.model_validate(row)
            for row in read_jsonl(source / "results.jsonl")
        ]
        for record in records:
            record.result.provider_request_id = None
            if record.result.error_message:
                record.result.error_message = sanitize_text(record.result.error_message)[:300]
        atomic_write_json(destination / "manifest.json", manifest)
        atomic_write_jsonl(destination / "results.jsonl", records)
        summary = self._summarize(run_id, records)
        atomic_write_json(destination / "summary.json", summary)
        return destination

    def _resolve_run_dir(self, run_id: str) -> Path:
        local = self.runs_dir / run_id
        if local.exists():
            return local
        if self.demo_dir.exists() and (self.demo_dir / "manifest.json").exists():
            demo = BenchmarkManifest.model_validate_json(
                (self.demo_dir / "manifest.json").read_text(encoding="utf-8")
            )
            if demo.run_id == run_id:
                return self.demo_dir
        raise FileNotFoundError(f"Benchmark run not found: {run_id}")
