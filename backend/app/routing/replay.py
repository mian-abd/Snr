from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import fmean

from app.domain.models import (
    BenchmarkRecord,
    CapabilitySpec,
    GenerationStatus,
    ModelSpec,
    PricingSpec,
    RoutingDashboard,
    RoutingPriority,
    RoutingStrategySummary,
)
from app.routing.policy import CHEAP_MODEL_ID, STRONG_MODEL_ID, RuleBasedRouter
from app.storage import read_jsonl


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


def _summarize(
    strategy_id: str, label: str, chosen: list[BenchmarkRecord]
) -> RoutingStrategySummary:
    successful = [row for row in chosen if row.result.status == GenerationStatus.SUCCESS]
    latencies = [row.result.latency_ms for row in successful]
    costs = [row.result.cost_usd for row in successful if row.result.cost_usd is not None]
    correct = sum(row.exact_match for row in chosen)
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
        total_cost_usd=sum(costs, Decimal("0")) if costs else None,
    )


def build_dashboard(demo_dir: Path) -> RoutingDashboard:
    """Replay CP1's saved model-by-prompt matrix without sending model requests."""
    records = [
        BenchmarkRecord.model_validate(row)
        for row in read_jsonl(demo_dir / "results.jsonl")
    ]
    if not records:
        raise FileNotFoundError("No saved benchmark records are available for routing replay")
    by_sample: dict[str, dict[str, BenchmarkRecord]] = defaultdict(dict)
    for record in records:
        by_sample[record.sample_id][record.result.requested_model_id] = record

    strategy_specs = [
        ("fixed_cheap", "Fixed baseline: cheaper/smaller model"),
        ("fixed_strong", "Fixed baseline: stronger model"),
        ("rule_cost", "Rule router: cost priority"),
        ("rule_quality", "Rule router: quality priority"),
        ("rule_latency", "Rule router: latency priority"),
        ("rule_balanced", "Rule router: balanced priority"),
    ]
    router = RuleBasedRouter()
    summaries: list[RoutingStrategySummary] = []
    for strategy_id, label in strategy_specs:
        selected: list[BenchmarkRecord] = []
        for sample_records in by_sample.values():
            exemplar = next(iter(sample_records.values()))
            if strategy_id == "fixed_cheap":
                model_id = CHEAP_MODEL_ID
            elif strategy_id == "fixed_strong":
                model_id = STRONG_MODEL_ID
            else:
                model_id = router.decide(
                    prompt=exemplar.rendered_prompt,
                    priority=RoutingPriority(strategy_id.removeprefix("rule_")),
                    models=_candidate_models(list(sample_records)),
                ).selected_model_id
            if model_id in sample_records:
                selected.append(sample_records[model_id])
        summaries.append(_summarize(strategy_id, label, selected))
    return RoutingDashboard(
        source_run_id=records[0].run_id,
        source_dataset=records[0].dataset,
        source_cells=len(records),
        note=(
            "Offline replay selects from the saved Checkpoint 1 result matrix. "
            "No provider calls are made."
        ),
        strategies=summaries,
    )
