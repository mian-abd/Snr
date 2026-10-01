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


class ComparisonRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=50_000)
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
    saved: bool
    created_at_utc: datetime = Field(default_factory=utc_now)
    results: list[GenerationResult]


class EligibilityRequest(StrictModel):
    min_context_tokens: int = Field(default=500_000, ge=1)


class EligibilityResult(StrictModel):
    model_id: str
    eligible: bool
    reasons: list[str]
    evaluated_requirements: EligibilityRequest
    model_snapshot_id: str


class EligibilityResponse(StrictModel):
    results: list[EligibilityResult]


class HealthResponse(StrictModel):
    status: str
    version: str
    registry_loaded: bool
    registry_snapshot_id: str | None
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


class PaginatedRecords(StrictModel):
    items: list[BenchmarkRecord]
    total: int
    offset: int
    limit: int
