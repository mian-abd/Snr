"""Run the Checkpoint 3 suite through the multi-provider pool and record every cell.

    uv run --project backend python -m app.benchmarks.suite_runner --smoke 2   # estimate only
    uv run --project backend python -m app.benchmarks.suite_runner --smoke 2 --confirm
    uv run --project backend python -m app.benchmarks.suite_runner --confirm   # all 600

Each model runs in its own paced worker, so a slow free endpoint never blocks the others.
Every attempt is appended as soon as it finishes and a run resumes where it stopped. Paid spend
is capped, and OpenRouter's account-wide free quota is respected.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values

from app.benchmarks.suite import SuiteItem, TaskGroup, file_sha256, load_suite
from app.benchmarks.tasks import (
    MAX_TOKENS,
    SUITE_PROMPT_VERSION,
    extract,
    max_tokens,
    render_prompt,
)
from app.config import REPOSITORY_ROOT
from app.domain.models import (
    ExperimentContext,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    StrictModel,
)
from app.providers.openai_compatible import OpenAICompatibleAdapter
from app.registry.pool import Access, PoolModel, PoolSnapshot, endpoint_for, load_pool
from app.storage import append_jsonl, atomic_write_json, read_jsonl

SUITE_PATH = REPOSITORY_ROOT / "data" / "benchmarks" / "cp3_suite.jsonl"
POOL_PATH = REPOSITORY_ROOT / "data" / "registry" / "cp3-pool-2026-10-27.json"
RUNS_DIR = REPOSITORY_ROOT / "data" / "local" / "cp3"
SPEND_CAP_USD = Decimal("15.00")
OPENROUTER_FREE_DAILY_CEILING = 950  # below the account's 1,000/day so live demos keep headroom
TIMEOUT_SECONDS = 180
RETRY_BACKOFF_SECONDS = {GenerationStatus.RATE_LIMITED: 65.0, GenerationStatus.TIMEOUT: 10.0}


class SuiteRecord(StrictModel):
    run_id: str
    pool_snapshot_id: str
    prompt_version: str
    sample_id: str
    benchmark: str
    task_group: TaskGroup
    router_split: str
    model_id: str
    access: Access
    result: GenerationResult
    extracted_answer: str | None
    extraction_method: str | None
    correct: bool | None
    scored_by: str | None


def _retryable(result: GenerationResult) -> bool:
    if result.status in {GenerationStatus.TIMEOUT, GenerationStatus.RATE_LIMITED}:
        return True
    if result.status != GenerationStatus.PROVIDER_ERROR:
        return False
    try:
        return int(result.error_code or "0") >= 500
    except ValueError:
        return True  # network-level failures


def worst_case_usd(model: PoolModel, item: SuiteItem) -> Decimal:
    system, prompt = render_prompt(item)
    prompt_tokens = Decimal((len(system or "") + len(prompt)) // 4 + 16)
    return (
        prompt_tokens * model.prompt_price_per_token
        + Decimal(max_tokens(item)) * model.completion_price_per_token
    ) * 2  # one retry


class Budget:
    """Shared, conservative spend and quota accounting across all workers."""

    def __init__(self, cap: Decimal, spent: Decimal, free_used_today: int) -> None:
        self.cap = cap
        self.spent = spent
        self.reserved = Decimal("0")
        self.free_used_today = free_used_today
        self.lock = asyncio.Lock()

    async def reserve(self, model: PoolModel, item: SuiteItem) -> Decimal | None:
        async with self.lock:
            if model.access == Access.FREE and model.provider == "openrouter":
                if self.free_used_today >= OPENROUTER_FREE_DAILY_CEILING:
                    return None
                self.free_used_today += 2  # reserve the retry too
            amount = worst_case_usd(model, item)
            if self.spent + self.reserved + amount > self.cap:
                return None
            self.reserved += amount
            return amount

    async def settle(
        self, reserved: Decimal, actual: Decimal, model: PoolModel, attempts: int
    ) -> None:
        async with self.lock:
            self.reserved -= reserved
            self.spent += actual
            if model.access == Access.FREE and model.provider == "openrouter":
                self.free_used_today -= 2 - attempts


class Pacer:
    """Space request starts to respect a requests-per-minute limit."""

    def __init__(self, requests_per_minute: float) -> None:
        self.interval = 60.0 / requests_per_minute
        self.next_start = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_start - now)
            self.next_start = max(now, self.next_start) + self.interval
        if delay:
            await asyncio.sleep(delay)


async def _run_cell(
    *,
    adapter: OpenAICompatibleAdapter,
    model: PoolModel,
    item: SuiteItem,
    run_id: str,
    snapshot: PoolSnapshot,
    pacer: Pacer,
    budget: Budget,
    model_dir: Path,
) -> SuiteRecord | None:
    reserved = await budget.reserve(model, item)
    if reserved is None:
        return None
    system, prompt = render_prompt(item)
    request = GenerationRequest(
        model_id=model.id,
        prompt=prompt,
        system_prompt=system,
        max_tokens=max_tokens(item),
        timeout_seconds=TIMEOUT_SECONDS,
        experiment_context=ExperimentContext(run_id=run_id, sample_id=item.sample_id),
    )
    final: GenerationResult | None = None
    actual = Decimal("0")
    attempts = 0
    for attempt in (1, 2):
        await pacer.wait()
        result = await adapter.generate(request, attempt_number=attempt)
        attempts = attempt
        actual += result.cost_usd or Decimal("0")
        append_jsonl(
            model_dir / "attempts.jsonl",
            {"sample_id": item.sample_id, "result": result.model_dump(mode="json")},
        )
        final = result
        if not _retryable(result) or attempt == 2:
            break
        await asyncio.sleep(RETRY_BACKOFF_SECONDS.get(result.status, 5.0))
    await budget.settle(reserved, actual, model, attempts)
    assert final is not None
    usable = final.status == GenerationStatus.SUCCESS
    extraction = extract(item, final.text if usable else None)
    record = SuiteRecord(
        run_id=run_id,
        pool_snapshot_id=snapshot.snapshot_id,
        prompt_version=SUITE_PROMPT_VERSION,
        sample_id=item.sample_id,
        benchmark=item.benchmark.value,
        task_group=item.task_group,
        router_split=item.router_split.value,
        model_id=model.id,
        access=model.access,
        result=final.model_copy(update={"provider_request_id": None}),
        extracted_answer=extraction.answer,
        extraction_method=extraction.method,
        # Failed calls are wrong for every task, code included; served code waits for EvalPlus.
        correct=extraction.correct if usable else False,
        scored_by=("exact" if item.task_group != TaskGroup.CODE else None) if usable else "failure",
    )
    append_jsonl(model_dir / "results.jsonl", record)
    return record


async def _run_model(
    model: PoolModel,
    items: list[SuiteItem],
    *,
    adapter: OpenAICompatibleAdapter,
    run_id: str,
    snapshot: PoolSnapshot,
    budget: Budget,
    run_dir: Path,
) -> Counter[str]:
    model_dir = run_dir / model.id
    done = {row["sample_id"] for row in read_jsonl(model_dir / "results.jsonl")}
    pending = [item for item in items if item.sample_id not in done]
    pacer = Pacer(model.requests_per_minute)
    slots = asyncio.Semaphore(model.max_concurrency)
    tally: Counter[str] = Counter(skipped=len(done))

    async def one(item: SuiteItem) -> None:
        async with slots:
            record = await _run_cell(
                adapter=adapter, model=model, item=item, run_id=run_id, snapshot=snapshot,
                pacer=pacer, budget=budget, model_dir=model_dir,
            )
        if record is None:
            tally["budget_stopped"] += 1
            return
        tally[record.result.status.value] += 1
        if record.correct:
            tally["correct"] += 1
        done_count = sum(tally[key] for key in tally if key not in {"skipped", "correct"})
        if done_count % 25 == 0:
            print(f"  {model.id}: {done_count}/{len(pending)} new cells", flush=True)

    await asyncio.gather(*(one(item) for item in pending))
    return tally


def _load_keys() -> dict[str, str]:
    values = dotenv_values(REPOSITORY_ROOT / "backend" / ".env")
    return {key: value for key, value in values.items() if value}


def _select_items(items: list[SuiteItem], smoke: int | None) -> list[SuiteItem]:
    if smoke is None:
        return items
    picked: list[SuiteItem] = []
    seen: Counter[str] = Counter()
    for item in items:
        if seen[item.benchmark.value] < smoke:
            picked.append(item)
            seen[item.benchmark.value] += 1
    return picked


async def run(args: argparse.Namespace) -> int:
    snapshot = load_pool(POOL_PATH)
    items = _select_items(load_suite(SUITE_PATH), args.smoke)
    keys = _load_keys()
    wanted = set(args.models.split(",")) if args.models else None
    models: list[PoolModel] = []
    for model in snapshot.models:
        if not model.enabled or (wanted and model.id not in wanted):
            continue
        if model.api_key_env and model.api_key_env not in keys:
            print(f"skip {model.id}: {model.api_key_env} is not set in backend/.env")
            continue
        models.append(model)
    estimate = sum(
        (worst_case_usd(model, item) for model in models for item in items), Decimal("0")
    )
    print(f"{len(items)} prompts x {len(models)} models; worst-case paid spend ${estimate:.2f}; "
          f"hard cap ${SPEND_CAP_USD}")
    if not args.confirm:
        print("Re-run with --confirm to make the calls.")
        return 0

    run_id = args.run_id or f"cp3-{'smoke' if args.smoke else 'full'}"
    run_dir = RUNS_DIR / run_id
    spent = sum(
        (
            Decimal(str(row["result"]["cost_usd"] or "0"))
            for path in run_dir.glob("*/attempts.jsonl")
            for row in read_jsonl(path)
        ),
        Decimal("0"),
    )
    budget = Budget(SPEND_CAP_USD, spent, free_used_today=args.free_used_today)
    adapter = OpenAICompatibleAdapter([endpoint_for(model) for model in models], keys=keys)
    # One manifest per model, so separate invocations can add models to the same run.
    for model in models:
        atomic_write_json(
            run_dir / model.id / "manifest.json",
            {
                "run_id": run_id,
                "model_id": model.id,
                "updated_at_utc": datetime.now(UTC).isoformat(),
                "pool_snapshot_id": snapshot.snapshot_id,
                "pool_models_sha256": snapshot.models_sha256,
                "suite_sha256": file_sha256(SUITE_PATH),
                "prompt_version": SUITE_PROMPT_VERSION,
                "temperature": 0,
                "max_tokens": {group.value: MAX_TOKENS[group] for group in TaskGroup},
                "timeout_seconds": TIMEOUT_SECONDS,
                "prompts": len(items),
                "spend_cap_usd": str(SPEND_CAP_USD),
            },
        )
    tallies = await asyncio.gather(
        *(
            _run_model(model, items, adapter=adapter, run_id=run_id, snapshot=snapshot,
                       budget=budget, run_dir=run_dir)
            for model in models
        )
    )
    for model, tally in zip(models, tallies, strict=True):
        print(f"{model.id}: {dict(tally)}")
    print(f"paid spend this run so far: ${budget.spent:.4f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Checkpoint 3 suite through the pool")
    parser.add_argument("--models", help="Comma-separated pool IDs (default: all with keys)")
    parser.add_argument("--smoke", type=int, help="Only the first N prompts of each benchmark")
    parser.add_argument("--run-id", help="Resume or name a run")
    parser.add_argument("--free-used-today", type=int, default=0,
                        help="OpenRouter free requests already used today")
    parser.add_argument("--confirm", action="store_true", help="Actually make the calls")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
