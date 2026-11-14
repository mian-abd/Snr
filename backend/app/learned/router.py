"""The integrated learned router (proposal week of Nov 5): no scikit-learn at serving time.

``app.learned.train`` selects the classifier on the validation split, refits it on the training
and validation splits, tunes one weight preset per user priority on validation, and exports what
a live router needs to ``data/learned/cp3-router-model.json``: the standardizer, coefficients,
model-history aggregates, and per-model cost, latency, and failure estimates. A decision here is
plain arithmetic over that file, so the console runs exactly the router the held-out test
measured.

Hard requirements come first: a model that the live catalog shows is no longer served, whose
context window is too small, or whose API key is not configured, is excluded before scoring.
When the live catalog reports a new price, the model's expected cost is scaled to it
(``live_expected_cost``); the classifier and the tuned weights stay exactly as evaluated.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.benchmarks.suite import TaskGroup
from app.config import REPOSITORY_ROOT
from app.domain.models import (
    CatalogSource,
    LearnedCandidate,
    LearnedRouteRequest,
    LearnedRoutingDecision,
    LiveCatalogStatus,
    LiveModelStatus,
    RoutingPriority,
    RoutingWeights,
    StrictModel,
    WhatIfChanges,
)
from app.learned.features import (
    ModelHistory,
    count_options,
    infer_task_group,
    model_features,
    text_features,
)
from app.registry.pool import PoolModel, PoolSnapshot
from app.routing.multi_objective import (
    CandidateEstimate,
    PolicyWeights,
    ScoredCandidate,
    score_candidates,
)
from app.routing.policy import prompt_signals

ROUTER_MODEL_FILE = Path("learned") / "cp3-router-model.json"  # relative to the data dir
ROUTER_POOL_FILE = Path("registry") / "cp3-pool-2026-10-27.json"
ROUTER_MODEL_PATH = REPOSITORY_ROOT / "data" / ROUTER_MODEL_FILE
STRATEGY_ID = "learned_logistic_v1"
PRIORITY_LABELS = {
    RoutingPriority.BALANCED: "balanced",
    RoutingPriority.COST: "lowest-cost",
    RoutingPriority.QUALITY: "best-quality",
    RoutingPriority.LATENCY: "fastest",
}


class NoEligibleModelError(ValueError):
    pass


class TaskEstimate(StrictModel):
    expected_cost_usd: float
    expected_latency_ms: float
    failure_rate: float


class RouterArtifact(StrictModel):
    """A trained linear router: standardized features, coefficients, and its routing inputs."""

    schema_version: str = "1.0"
    artifact_id: str
    run_id: str
    pool_snapshot_id: str
    family: str
    params: dict[str, int | float]
    selection_rule: str
    trained_on_splits: list[str]
    training_rows: int
    model_ids: list[str]
    features: list[str]
    scaler_mean: list[float]
    scaler_scale: list[float]
    coefficients: list[float]
    intercept: float
    history: dict[str, Any]
    estimates: dict[str, dict[TaskGroup, TaskEstimate]]
    weights: dict[RoutingPriority, RoutingWeights]


def prompt_token_estimate(text: str) -> int:
    """The same rough count the benchmark runner budgets with: four characters per token."""
    return len(text) // 4 + 16


def live_expected_cost(
    expected_cost_usd: float,
    status: LiveModelStatus | None,
    prompt_tokens: float,
    output_tokens: float,
) -> float:
    """Scale a historical expected cost to the live price for this prompt's token mix."""
    if (
        status is None
        or status.live_prompt_price_per_million is None
        or status.live_completion_price_per_million is None
    ):
        return expected_cost_usd
    snapshot = (
        prompt_tokens * status.snapshot_prompt_price_per_million
        + output_tokens * status.snapshot_completion_price_per_million
    )
    live = (
        prompt_tokens * status.live_prompt_price_per_million
        + output_tokens * status.live_completion_price_per_million
    )
    if snapshot > 0:
        return expected_cost_usd * live / snapshot
    return live / 1_000_000  # a free model that started charging: price one typical call


def policy_weights(weights: RoutingWeights) -> PolicyWeights:
    return PolicyWeights(
        quality=weights.quality,
        cost=weights.cost,
        latency=weights.latency,
        reliability=weights.reliability,
    )


class LearnedRouter:
    def __init__(self, artifact: RouterArtifact, pool: PoolSnapshot) -> None:
        if artifact.pool_snapshot_id != pool.snapshot_id:
            raise ValueError(
                f"Router was trained on {artifact.pool_snapshot_id}, not {pool.snapshot_id}"
            )
        by_id = {model.id: model for model in pool.models}
        missing = set(artifact.model_ids) - set(by_id)
        if missing:
            raise ValueError(f"Pool snapshot lacks trained models: {sorted(missing)}")
        self.artifact = artifact
        self.pool = pool
        self.models: dict[str, PoolModel] = {
            model_id: by_id[model_id] for model_id in artifact.model_ids
        }
        self.pool_ids = sorted(artifact.model_ids)
        self.history = ModelHistory.from_snapshot(artifact.history)

    def p_success(self, text: str, group: TaskGroup, option_count: int, model: PoolModel) -> float:
        row = {
            **text_features(text, group, option_count),
            **model_features(model, group, self.history, self.pool_ids, exclude_sample=None),
        }
        art = self.artifact
        z = art.intercept + sum(
            coefficient * (row[name] - mean) / scale
            for name, mean, scale, coefficient in zip(
                art.features, art.scaler_mean, art.scaler_scale, art.coefficients, strict=True
            )
        )
        return 1.0 / (1.0 + math.exp(-z))

    def decide_for(
        self,
        text: str,
        *,
        group: TaskGroup,
        option_count: int,
        weights: RoutingWeights,
        min_context_tokens: int = 1,
        configured_keys: set[str] | None = None,
        catalog: LiveCatalogStatus | None = None,
        changes: WhatIfChanges | None = None,
    ) -> tuple[str, list[LearnedCandidate]]:
        """Score every model; ``configured_keys=None`` skips the credential check (offline).

        ``catalog`` applies the live catalog: unavailable models are excluded and expected costs
        follow live prices. Without it the router behaves exactly as it was evaluated.
        ``changes`` applies hypothetical conditions on top, for what-if previews.
        """
        live = {status.model_id: status for status in catalog.models} if catalog else {}
        prompt_tokens = prompt_token_estimate(text)
        candidates: list[LearnedCandidate] = []
        for model_id in self.pool_ids:
            model = self.models[model_id]
            estimate = self.artifact.estimates[model_id][group]
            status = live.get(model_id)
            exclusion = None
            if status is not None and not status.available:
                exclusion = f"Unavailable now: {status.note}"
            elif changes is not None and model_id in changes.unavailable:
                exclusion = "What-if: marked unavailable"
            elif model.context_length < min_context_tokens:
                exclusion = (
                    f"Context {model.context_length:,} is below the required "
                    f"{min_context_tokens:,} tokens"
                )
            elif (
                configured_keys is not None
                and model.api_key_env
                and model.api_key_env not in configured_keys
            ):
                exclusion = f"{model.api_key_env} is not configured on the server"
            expected_cost = live_expected_cost(
                estimate.expected_cost_usd,
                status,
                prompt_tokens,
                self.history.output_tokens.get((model_id, group), 512.0),
            )
            repriced = abs(expected_cost - estimate.expected_cost_usd) > 1e-15
            latency = estimate.expected_latency_ms
            failure = estimate.failure_rate
            if changes is not None:
                expected_cost *= changes.price_multipliers.get(model_id, 1.0)
                latency *= changes.latency_multipliers.get(model_id, 1.0)
                failure = 1 - (1 - failure) * (1 - changes.failure_shares.get(model_id, 0.0))
            changed = status is not None and (
                not status.available or repriced or bool(status.missing_hosts)
            )
            candidates.append(
                LearnedCandidate(
                    model_id=model_id,
                    display_name=model.display_name,
                    access=model.access.value,
                    provider=model.provider,
                    context_length=model.context_length,
                    data_policy=model.data_policy,
                    eligible=exclusion is None,
                    exclusion_reason=exclusion,
                    p_success=self.p_success(text, group, option_count, model),
                    expected_cost_usd=expected_cost,
                    expected_latency_ms=latency,
                    failure_rate=failure,
                    snapshot_expected_cost_usd=estimate.expected_cost_usd if repriced else None,
                    catalog_note=status.note if changed and status is not None else None,
                    what_if_note=changes.describe(model_id) if changes is not None else None,
                )
            )
        eligible = [item for item in candidates if item.eligible]
        if not eligible:
            raise NoEligibleModelError("No model satisfies the hard requirements")
        scored = {item.model_id: item for item in self._score(eligible, weights)}
        ranked = list(scored)
        candidates = [
            item.model_copy(
                update={
                    "score": scored[item.model_id].score,
                    "quality_term": scored[item.model_id].quality_term,
                    "cost_penalty": scored[item.model_id].cost_penalty,
                    "latency_penalty": scored[item.model_id].latency_penalty,
                    "reliability_penalty": scored[item.model_id].reliability_penalty,
                }
            )
            if item.model_id in scored
            else item
            for item in candidates
        ]
        return ranked[0], candidates

    @staticmethod
    def _score(eligible: list[LearnedCandidate], weights: RoutingWeights) -> list[ScoredCandidate]:
        return score_candidates(
            [
                CandidateEstimate(
                    model_id=item.model_id,
                    p_success=item.p_success,
                    expected_cost_usd=item.expected_cost_usd,
                    expected_latency_ms=item.expected_latency_ms,
                    failure_rate=item.failure_rate,
                )
                for item in eligible
            ],
            policy_weights(weights),
        )

    def decide(
        self,
        request: LearnedRouteRequest,
        configured_keys: set[str],
        catalog: LiveCatalogStatus | None = None,
        changes: WhatIfChanges | None = None,
    ) -> LearnedRoutingDecision:
        group = request.task_group or infer_task_group(request.prompt)
        weights = request.weights or self.artifact.weights[request.priority]
        selected, candidates = self.decide_for(
            request.prompt,
            group=group,
            option_count=count_options(request.prompt),
            weights=weights,
            min_context_tokens=request.min_context_tokens,
            configured_keys=configured_keys,
            catalog=catalog,
            changes=changes,
        )
        chosen = next(item for item in candidates if item.model_id == selected)
        preset = (
            "custom weights"
            if request.weights
            else f"the tuned {PRIORITY_LABELS[request.priority]} preset"
        )
        reason = (
            f"Highest score under {preset}: predicted success {chosen.p_success:.0%}, "
            f"expected cost ${chosen.expected_cost_usd:.5f}, "
            f"expected latency {chosen.expected_latency_ms / 1000:.1f} s for {group.value} prompts."
        )
        if catalog is not None and changes is None:
            # The same request with the dated snapshot: every other requirement still applies.
            unaware, _ = self.decide_for(
                request.prompt,
                group=group,
                option_count=count_options(request.prompt),
                weights=weights,
                min_context_tokens=request.min_context_tokens,
                configured_keys=configured_keys,
            )
            gone = {status.model_id for status in catalog.models if not status.available}
            if unaware in gone:
                reason += (
                    f" Without the live catalog check it would have chosen "
                    f"{self.models[unaware].display_name}, which is no longer served."
                )
            elif unaware != selected:
                reason += (
                    f" At the snapshot's prices it would have chosen "
                    f"{self.models[unaware].display_name}."
                )
        return LearnedRoutingDecision(
            strategy_id=STRATEGY_ID,
            artifact_id=self.artifact.artifact_id,
            pool_snapshot_id=self.artifact.pool_snapshot_id,
            priority=request.priority,
            weights=weights,
            custom_weights=request.weights is not None,
            task_group=group,
            task_group_inferred=request.task_group is None,
            task_signals=prompt_signals(request.prompt),
            min_context_tokens=request.min_context_tokens,
            selected_model_id=selected,
            candidates=candidates,
            reason=reason,
            catalog_source=catalog.source if catalog else CatalogSource.OFF,
            catalog_checked_at_utc=catalog.checked_at_utc if catalog else None,
        )


def load_router(artifact_path: Path, pool: PoolSnapshot) -> LearnedRouter:
    artifact = RouterArtifact.model_validate_json(artifact_path.read_text(encoding="utf-8"))
    return LearnedRouter(artifact, pool)
