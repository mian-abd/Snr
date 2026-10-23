"""Collect the Checkpoint 2 paid-pool GSM8K matrix behind an explicit cost estimate.

Usage (from the repository root):

    uv run --project backend python -m app.benchmarks.paid_matrix --mode pilot
    uv run --project backend python -m app.benchmarks.paid_matrix --mode full --confirm

Without ``--confirm`` the command only prints the worst-case estimate. The same fixed
12-question sample, prompt template, generation settings, and scorer as Checkpoint 1 are
reused; only the model pool changes, so the two matrices stay comparable.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.benchmarks.costs import (
    PAID_BUDGET_FILE,
    PAID_DEMO_NAME,
    PAID_MAX_REQUESTS,
    PAID_RUN_PREFIX,
    SPEND_CAP_USD,
    estimate_worst_case_usd,
)
from app.benchmarks.gsm8k import load_samples
from app.benchmarks.runner import BenchmarkRunner
from app.config import REPOSITORY_ROOT, get_settings
from app.domain.models import BenchmarkMode
from app.providers import GenerationService
from app.registry import ModelRegistry
from app.state import PAID_MODEL_IDS, PAID_REGISTRY_PATH


async def _run(mode: BenchmarkMode, run_id: str | None) -> int:
    settings = get_settings()
    if not settings.credential_configured:
        print("OPENROUTER_API_KEY is not configured in backend/.env", file=sys.stderr)
        return 2
    assert settings.openrouter_api_key is not None
    from app.providers.litellm_openrouter import LiteLLMOpenRouterAdapter

    registry = ModelRegistry(
        PAID_REGISTRY_PATH, expected_model_ids=PAID_MODEL_IDS, require_free=False
    )
    api_key = settings.openrouter_api_key.get_secret_value()
    adapter = LiteLLMOpenRouterAdapter(
        api_key=api_key,
        registry=registry,
        site_url=settings.openrouter_site_url,
        app_name=settings.openrouter_app_name,
    )
    runner = BenchmarkRunner(
        service=GenerationService(adapter),
        registry=registry,
        data_dir=settings.data_dir,
        api_key=api_key,
        max_daily_requests=PAID_MAX_REQUESTS,
        repository_root=REPOSITORY_ROOT,
        demo_name=PAID_DEMO_NAME,
        run_prefix=PAID_RUN_PREFIX,
        budget_file=PAID_BUDGET_FILE,
    )
    view = await runner.run(mode, run_id)
    manifest = view.manifest
    print(f"run_id={manifest.run_id} status={manifest.status.value}")
    print(
        f"cells={manifest.completed_cells}/{manifest.total_cells} "
        f"successful={manifest.successful_cells} failed={manifest.failed_cells}"
    )
    if view.summary:
        for model in view.summary.models:
            print(
                f"{model.model_id}: correct={model.correct}/{model.attempted} "
                f"median_ms={model.median_latency_ms} cost_usd={model.total_cost_usd}"
            )
    if mode == BenchmarkMode.FULL and manifest.completed_cells == manifest.total_cells:
        destination = runner.sanitize_run(manifest.run_id)
        print(f"sanitized evidence written to {destination.relative_to(REPOSITORY_ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["pilot", "full"], default="pilot")
    parser.add_argument("--run-id", default=None, help="Resume an existing paid run")
    parser.add_argument("--confirm", action="store_true", help="Spend money after the estimate")
    args = parser.parse_args()
    mode = BenchmarkMode(args.mode)

    registry = ModelRegistry(
        PAID_REGISTRY_PATH, expected_model_ids=PAID_MODEL_IDS, require_free=False
    )
    samples = load_samples(REPOSITORY_ROOT / "data" / "benchmarks" / "gsm8k_checkpoint1.jsonl")
    if mode == BenchmarkMode.PILOT:
        samples = samples[:2]
    estimate = estimate_worst_case_usd(registry.models, samples)
    cells = len(samples) * len(registry.models)
    print(
        f"{mode.value}: {cells} cells, worst-case estimate ${estimate:.4f} "
        f"(cap ${SPEND_CAP_USD})"
    )
    if estimate > SPEND_CAP_USD:
        print("Estimate exceeds the project spending cap; refusing to run.", file=sys.stderr)
        return 3
    if not args.confirm:
        print("Re-run with --confirm to make the paid requests.")
        return 0
    return asyncio.run(_run(mode, args.run_id))


if __name__ == "__main__":
    raise SystemExit(main())
