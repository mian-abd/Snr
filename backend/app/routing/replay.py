from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import fmean, median

from app.domain.models import (
    BenchmarkRecord,
    CapabilitySpec,
    GenerationStatus,
    ModelSpec,
    PricingSpec,
    ReplayCell,
    ReplayPrompt,
    ReplaySelection,
    RoutingDashboard,
    RoutingPool,
    RoutingPriority,
    RoutingStrategySummary,
)
from app.routing.policy import (
    CHEAP_MODEL_ID,
    PAID_BUDGET_MODEL_ID,
    PAID_QUALITY_MODEL_ID,
    STRONG_MODEL_ID,
    RuleBasedRouter,
    prompt_signals,
)
from app.storage import read_jsonl

EVIDENCE_DIRS = {
    RoutingPool.BASELINE: "checkpoint-1",
    RoutingPool.PAID: "checkpoint-2-paid",
}
FIXED_MODELS = {
    RoutingPool.BASELINE: (CHEAP_MODEL_ID, STRONG_MODEL_ID),
    RoutingPool.PAID: (PAID_BUDGET_MODEL_ID, PAID_QUALITY_MODEL_ID),
}
STRATEGY_SPECS = (
    ("fixed_cheap", "Fixed baseline: lowest-cost model"),
    ("fixed_strong", "Fixed baseline: higher-capability model"),
    ("rule_cost", "Rule router: cost priority"),
    ("rule_quality", "Rule router: quality priority"),
    ("rule_latency", "Rule router: latency priority"),
    ("rule_balanced", "Rule router: balanced priority"),
)


def _candidate_models(model_ids: list[str]) -> list[ModelSpec]:
    """Replay needs IDs and prompt signals; metadata remains frozen in the registry."""
    return [
        ModelSpec(
            id=model_id,
            display_name=model_id,
            provider=model_id.split("/", maxsplit=1)[0],
            context_length=1_000_000,
            pricing=PricingSpec(),
            input_modalities=["text"],
            output_modalities=["text"],
            supported_parameters=[],
            capabilities=CapabilitySpec(),
            snapshot_id="replay",
            metadata_as_of=datetime(2026, 10, 1, tzinfo=UTC),
            source_url="replay",
        )
        for model_id in model_ids
    ]


def _p95(values: list[float]) -> float | None:
    """Nearest-rank 95th percentile; with 12 prompts this is the slowest served call."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _summarize(
    strategy_id: str, label: str, chosen: list[BenchmarkRecord]
) -> RoutingStrategySummary:
    successful = [row for row in chosen if row.result.status == GenerationStatus.SUCCESS]
    latencies = [row.result.latency_ms for row in successful]
    costs = [row.result.cost_usd for row in chosen if row.result.cost_usd is not None]
    correct = sum(row.exact_match for row in chosen)
    total_cost = sum(costs, Decimal("0")) if costs else None
    return RoutingStrategySummary(
        strategy_id=strategy_id,
        label=label,
        selected_model_counts=dict(Counter(row.result.requested_model_id for row in chosen)),
        attempted=len(chosen),
        successful=len(successful),
        failed=len(chosen) - len(successful),
        correct=correct,
        accuracy=correct / len(chosen) if chosen else 0,
        accuracy_when_served=(correct / len(successful) if successful else None),
        mean_latency_ms=fmean(latencies) if latencies else None,
        median_latency_ms=median(latencies) if latencies else None,
        p95_latency_ms=_p95(latencies),
        total_cost_usd=total_cost,
        cost_per_correct_usd=(
            total_cost / correct if total_cost is not None and correct else None
        ),
    )


def _question(rendered_prompt: str) -> str:
    return rendered_prompt.split("\n\n", maxsplit=1)[-1].strip()


def build_dashboard(
    demo_dir: Path, pool: RoutingPool = RoutingPool.BASELINE
) -> RoutingDashboard:
    """Replay a saved model-by-prompt matrix without sending model requests."""
    records = [
        BenchmarkRecord.model_validate(row)
        for row in read_jsonl(demo_dir / "results.jsonl")
    ]
    if not records:
        raise FileNotFoundError("No saved benchmark records are available for routing replay")
    model_ids = list(dict.fromkeys(record.result.requested_model_id for record in records))
    by_sample: dict[str, dict[str, BenchmarkRecord]] = defaultdict(dict)
    for record in records:
        by_sample[record.sample_id][record.result.requested_model_id] = record

    cheap_id, strong_id = FIXED_MODELS[pool]
    candidates = _candidate_models(model_ids)
    router = RuleBasedRouter()
    chosen: dict[str, list[BenchmarkRecord]] = {
        strategy_id: [] for strategy_id, _ in STRATEGY_SPECS
    }
    prompts: list[ReplayPrompt] = []
    for sample_records in by_sample.values():
        exemplar = next(iter(sample_records.values()))
        selections: list[ReplaySelection] = []
        for strategy_id, _ in STRATEGY_SPECS:
            if strategy_id == "fixed_cheap":
                model_id, reason = cheap_id, "Fixed baseline always selects the lowest-cost model."
            elif strategy_id == "fixed_strong":
                model_id = strong_id
                reason = "Fixed baseline always selects the higher-capability model."
            else:
                decision = router.decide(
                    prompt=exemplar.rendered_prompt,
                    priority=RoutingPriority(strategy_id.removeprefix("rule_")),
                    pool=pool,
                    models=candidates,
                )
                model_id, reason = decision.selected_model_id, decision.reason
            selections.append(
                ReplaySelection(strategy_id=strategy_id, model_id=model_id, reason=reason)
            )
            if model_id in sample_records:
                chosen[strategy_id].append(sample_records[model_id])
        prompts.append(
            ReplayPrompt(
                sample_id=exemplar.sample_id,
                source_index=exemplar.source_index,
                question=_question(exemplar.rendered_prompt),
                task_signals=prompt_signals(exemplar.rendered_prompt),
                cells=[
                    ReplayCell(
                        model_id=model_id,
                        status=sample_records[model_id].result.status,
                        correct=bool(sample_records[model_id].exact_match),
                        latency_ms=sample_records[model_id].result.latency_ms,
                        cost_usd=sample_records[model_id].result.cost_usd,
                    )
                    for model_id in model_ids
                    if model_id in sample_records
                ],
                selections=selections,
            )
        )

    source = (
        "the saved Checkpoint 1 free-tier matrix"
        if pool == RoutingPool.BASELINE
        else "the saved Checkpoint 2 paid-pool matrix"
    )
    return RoutingDashboard(
        pool=pool,
        source_run_id=records[0].run_id,
        source_dataset=records[0].dataset,
        source_cells=len(records),
        model_ids=model_ids,
        note=f"Offline replay selects from {source}. No provider calls are made.",
        strategies=[
            _summarize(strategy_id, label, chosen[strategy_id])
            for strategy_id, label in STRATEGY_SPECS
        ],
        prompts=prompts,
    )
