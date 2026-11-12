from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PricingSpec(StrictModel):
    prompt_per_token: Decimal | None = None
    completion_per_token: Decimal | None = None


class CapabilitySpec(StrictModel):
    tools: bool = False
    structured_output: bool = False


class ModelSpec(StrictModel):
    id: str
    display_name: str
    provider: str
    context_length: int = Field(gt=0)
    pricing: PricingSpec
    input_modalities: list[str]
    output_modalities: list[str]
    supported_parameters: list[str]
    capabilities: CapabilitySpec
    enabled: bool = True
    snapshot_id: str
    metadata_as_of: datetime
    source_url: str


class RegistrySnapshot(StrictModel):
    schema_version: str = "1.0"
    snapshot_id: str
    metadata_as_of: datetime
    source_url: str
    models_sha256: str
    models: list[ModelSpec]


class GenerationStatus(StrEnum):
    SUCCESS = "success"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    INVALID_RESPONSE = "invalid_response"
    MODEL_MISMATCH = "model_mismatch"


class CostSource(StrEnum):
    PROVIDER = "provider"
    REGISTRY_CALCULATION = "registry_calculation"
    UNAVAILABLE = "unavailable"


class ExperimentContext(StrictModel):
    run_id: str | None = None
    sample_id: str | None = None


class GenerationRequest(StrictModel):
    request_id: UUID = Field(default_factory=uuid4)
    model_id: str
    prompt: str = Field(min_length=1, max_length=50_000)
    system_prompt: str | None = None
    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    timeout_seconds: float = Field(default=90, ge=1, le=300)
    experiment_context: ExperimentContext | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class GenerationResult(StrictModel):
    request_id: UUID
    requested_model_id: str
    served_model_id: str | None = None
    provider: str = "openrouter"
    status: GenerationStatus
    text: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float = Field(ge=0)
    cost_usd: Decimal | None = None
    cost_source: CostSource = CostSource.UNAVAILABLE
    provider_request_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at_utc: datetime
    completed_at_utc: datetime
    attempt_number: int = Field(ge=1, le=2)


class GenerationOutcome(StrictModel):
    final: GenerationResult
    attempts: list[GenerationResult]


class RoutingPool(StrEnum):
    BASELINE = "baseline"
    PAID = "paid"


class ComparisonRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=50_000)
    pool: RoutingPool = RoutingPool.BASELINE
    save: bool = False

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class ComparisonResponse(StrictModel):
    comparison_id: UUID = Field(default_factory=uuid4)
    prompt: str
    pool: RoutingPool = RoutingPool.BASELINE
    saved: bool
    created_at_utc: datetime = Field(default_factory=utc_now)
    results: list[GenerationResult]


class RoutingPriority(StrEnum):
    COST = "cost"
    QUALITY = "quality"
    LATENCY = "latency"
    BALANCED = "balanced"


class TaskGroup(StrEnum):
    MATH = "math"
    QA = "qa"
    CODE = "code"


class RouteRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=50_000)
    priority: RoutingPriority = RoutingPriority.BALANCED
    pool: RoutingPool = RoutingPool.BASELINE
    min_context_tokens: int = Field(default=1, ge=1)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class RoutingDecision(StrictModel):
    strategy_id: str
    pool: RoutingPool
    priority: RoutingPriority
    min_context_tokens: int
    selected_model_id: str
    eligible_model_ids: list[str]
    task_signals: list[str]
    reason: str


class RoutingValidationCase(StrictModel):
    case_id: str
    label: str
    prompt: str
    priority: RoutingPriority
    min_context_tokens: int
    expected_model_id: str
    decision: RoutingDecision
    passed: bool


class RoutingValidationReport(StrictModel):
    strategy_id: str
    registry_snapshot_id: str
    passed: bool
    passed_cases: int
    total_cases: int
    cases: list[RoutingValidationCase]


class RouteResponse(StrictModel):
    decision: RoutingDecision
    result: GenerationResult


class RoutingStrategySummary(StrictModel):
    strategy_id: str
    label: str
    selected_model_counts: dict[str, int]
    attempted: int
    successful: int
    failed: int
    correct: int
    accuracy: float
    accuracy_when_served: float | None
    mean_latency_ms: float | None
    median_latency_ms: float | None
    p95_latency_ms: float | None
    total_cost_usd: Decimal | None
    cost_per_correct_usd: Decimal | None


class ReplayCell(StrictModel):
    """One saved model outcome for one benchmark prompt."""

    model_id: str
    status: GenerationStatus
    correct: bool
    latency_ms: float
    cost_usd: Decimal | None


class ReplaySelection(StrictModel):
    strategy_id: str
    model_id: str
    reason: str


class ReplayPrompt(StrictModel):
    sample_id: str
    source_index: int
    question: str
    task_signals: list[str]
    cells: list[ReplayCell]
    selections: list[ReplaySelection]


class RoutingDashboard(StrictModel):
    pool: RoutingPool
    source_run_id: str
    source_dataset: str
    source_cells: int
    model_ids: list[str]
    note: str
    strategies: list[RoutingStrategySummary]
    prompts: list[ReplayPrompt]


class ClassifierMetrics(StrictModel):
    log_loss: float
    brier: float
    roc_auc: float | None
    accuracy_at_0_5: float
    rows: int


class ClassifierTrial(StrictModel):
    params: dict[str, int | float]
    train: ClassifierMetrics
    validation: ClassifierMetrics


class ClassifierReport(StrictModel):
    best_params: dict[str, int | float]
    train: ClassifierMetrics
    validation: ClassifierMetrics
    overfit_gap_log_loss: float
    grid: list[ClassifierTrial]


class LearnedMatrixRow(StrictModel):
    """One model's scored outcomes over the whole Checkpoint 3 suite (every split)."""

    model_id: str
    display_name: str
    access: str
    prompts: int
    correct: int
    prompts_by_task: dict[str, int]
    correct_by_task: dict[str, int]
    failed_calls: int
    median_latency_ms: float | None
    cost_usd: float


class RoutingWeights(StrictModel):
    """Multi-objective weights for the learned router. Quality must count for something."""

    quality: float = Field(default=1.0, gt=0, le=10)
    cost: float = Field(ge=0, le=10)
    latency: float = Field(ge=0, le=10)
    reliability: float = Field(default=0.0, ge=0, le=10)


class StrategyTaskOutcome(StrictModel):
    prompts: int
    correct: int
    accuracy: float
    total_cost_usd: float
    median_latency_ms: float | None


class LearnedStrategyOutcome(StrictModel):
    strategy_id: str
    prompts: int
    correct: int
    accuracy: float
    total_cost_usd: float
    cost_per_correct_usd: float | None
    median_latency_ms: float | None
    p95_latency_ms: float | None
    selected_models: dict[str, int]
    by_task: dict[str, StrategyTaskOutcome] = Field(default_factory=dict)


class WeightTuningResult(StrictModel):
    """One priority's preset, chosen on the validation split."""

    priority: RoutingPriority
    weights: RoutingWeights
    validation_correct: int
    validation_cost_usd: float
    validation_median_latency_ms: float | None
    accuracy_floor: int | None
    candidates_tried: int


class RoutingErrorExample(StrictModel):
    kind: str  # "under" or "over"
    sample_id: str
    task_group: TaskGroup
    chosen_model_id: str
    alternative_model_id: str


class RoutingErrorSummary(StrictModel):
    """Proposal: under-routing picks a cheaper model that fails while a costlier eligible model
    succeeds; over-routing picks a costlier model although a cheaper eligible one also succeeds."""

    strategy_id: str
    prompts: int
    wrong: int
    under_routed: int
    over_routed: int
    examples: list[RoutingErrorExample]


class HeldoutEvaluation(StrictModel):
    """The selected router, refit on train + validation, evaluated once on the test split."""

    artifact_id: str
    trained_on: list[str]
    prompts: int
    classifier: ClassifierMetrics
    reference_model_task_prior: ClassifierMetrics
    strategies: list[LearnedStrategyOutcome]
    oracle: list[LearnedStrategyOutcome] = Field(default_factory=list)
    routing_errors: list[RoutingErrorSummary] = Field(default_factory=list)


class LearnedRouterReport(StrictModel):
    """The Checkpoint 3 matrix, classifier comparison, validation replay, and held-out test."""

    run_id: str
    pool_snapshot_id: str
    models: list[str]
    models_without_results: list[str]
    features: list[str]
    rows: dict[str, int]
    matrix: list[LearnedMatrixRow]
    classifiers: dict[str, ClassifierReport]
    reference_model_task_prior: ClassifierMetrics
    selected_family: str
    selection_rule: str
    validation_prompts: int
    strategies: list[LearnedStrategyOutcome]
    weight_tuning: list[WeightTuningResult]
    heldout: HeldoutEvaluation
    note: str


class LearnedRouteRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=50_000)
    priority: RoutingPriority = RoutingPriority.BALANCED
    weights: RoutingWeights | None = None  # overrides the priority's tuned preset
    task_group: TaskGroup | None = None  # inferred from the prompt when absent
    min_context_tokens: int = Field(default=1, ge=1)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class LearnedCandidate(StrictModel):
    model_id: str
    display_name: str
    access: str
    provider: str
    context_length: int
    data_policy: str
    eligible: bool
    exclusion_reason: str | None
    p_success: float
    expected_cost_usd: float
    expected_latency_ms: float
    failure_rate: float
    score: float | None = None
    quality_term: float | None = None
    cost_penalty: float | None = None
    latency_penalty: float | None = None
    reliability_penalty: float | None = None


class LearnedRoutingDecision(StrictModel):
    strategy_id: str
    artifact_id: str
    pool_snapshot_id: str
    priority: RoutingPriority
    weights: RoutingWeights
    custom_weights: bool
    task_group: TaskGroup
    task_group_inferred: bool
    task_signals: list[str]
    min_context_tokens: int
    selected_model_id: str
    candidates: list[LearnedCandidate]
    reason: str


class LearnedRouteResponse(StrictModel):
    decision: LearnedRoutingDecision
    result: GenerationResult


class EligibilityRequest(StrictModel):
    min_context_tokens: int = Field(default=500_000, ge=1)
    # None evaluates every registered pool.
    pool: RoutingPool | None = None


class EligibilityResult(StrictModel):
    model_id: str
    eligible: bool
    reasons: list[str]
    evaluated_requirements: EligibilityRequest
    model_snapshot_id: str
    pool: RoutingPool | None = None


class EligibilityResponse(StrictModel):
    results: list[EligibilityResult]


class HealthResponse(StrictModel):
    status: str
    version: str
    registry_loaded: bool
    registry_snapshot_id: str | None
    routing_registry_snapshot_id: str | None = None
    credential_configured: bool
    active_benchmark_run_id: str | None


class BenchmarkMode(StrEnum):
    PILOT = "pilot"
    FULL = "full"


class BenchmarkStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    BUDGET_PAUSED = "budget_paused"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class BenchmarkSample(StrictModel):
    dataset: str
    configuration: str
    revision: str
    split: str
    source_index: int
    sample_id: str
    question: str
    canonical_answer: str
    expected_answer: str
    selection_seed: int


class BenchmarkRecord(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    mode: BenchmarkMode
    dataset: str
    configuration: str
    revision: str
    split: str
    source_index: int
    sample_id: str
    prompt_template_version: str
    rendered_prompt: str
    expected_answer: str
    extracted_answer: str | None
    extraction_method: str | None
    exact_match: int
    result: GenerationResult
    model_snapshot_id: str
    generation_config_hash: str


class ModelBenchmarkSummary(StrictModel):
    model_id: str
    attempted: int
    successful: int
    failed: int
    correct: int
    accuracy: float
    mean_latency_ms: float | None
    median_latency_ms: float | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost_usd: Decimal | None
    error_counts: dict[str, int]


class BenchmarkSummary(StrictModel):
    run_id: str
    generated_at_utc: datetime
    models: list[ModelBenchmarkSummary]


class BenchmarkManifest(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    mode: BenchmarkMode
    status: BenchmarkStatus
    dataset: str
    dataset_revision: str
    registry_snapshot_id: str
    registry_models_sha256: str
    model_ids: list[str]
    generation_config: dict[str, Any]
    generation_config_hash: str
    git_commit: str | None
    total_cells: int
    completed_cells: int = 0
    successful_cells: int = 0
    failed_cells: int = 0
    created_at_utc: datetime
    updated_at_utc: datetime
    error_message: str | None = None


class BenchmarkRunView(StrictModel):
    manifest: BenchmarkManifest
    summary: BenchmarkSummary | None = None


class BenchmarkStartRequest(StrictModel):
    mode: BenchmarkMode = BenchmarkMode.FULL
    pool: RoutingPool = RoutingPool.BASELINE
    # Paid runs must echo the estimate the user confirmed; the server recomputes and compares.
    confirmed_estimate_usd: Decimal | None = None


class BenchmarkEstimate(StrictModel):
    pool: RoutingPool
    mode: BenchmarkMode
    model_ids: list[str]
    samples: int
    cells: int
    worst_case_usd: Decimal
    spend_cap_usd: Decimal | None
    within_cap: bool
    requires_confirmation: bool


class PaginatedRecords(StrictModel):
    items: list[BenchmarkRecord]
    total: int
    offset: int
    limit: int
