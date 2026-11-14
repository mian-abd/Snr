"""The flagship extension's report (week of Nov 19): a second router with flagship models."""

from __future__ import annotations

from app.domain.models import (
    ClassifierMetrics,
    ClassifierReport,
    EvaluationSet,
    LearnedMatrixRow,
    StrictModel,
    WeightTuningResult,
)
from app.registry.pool import PoolModel


class FlagshipRouter(StrictModel):
    """The second router: the Checkpoint 3 recipe refit with the flagship models in the pool."""

    artifact_id: str
    family: str
    params: dict[str, int | float]
    selection_rule: str
    training_rows: int
    features: int
    classifiers: dict[str, ClassifierReport]
    reference_model_task_prior: ClassifierMetrics
    validation_prompts: int
    weight_tuning: list[WeightTuningResult]


class ExcludedFlagship(StrictModel):
    """A flagship that did not answer every prompt, so neither router can be fit with it."""

    model_id: str
    display_name: str
    prompts_scored: int
    prompts_total: int
    spend_usd: float
    reason: str


class FlagshipStudyReport(StrictModel):
    """Week of Nov 19 extension: does adding flagship models to the pool pay off?"""

    title: str
    question: str
    flagship_snapshot_id: str
    flagships: list[PoolModel]  # the ones that answered every prompt
    excluded_flagships: list[ExcludedFlagship]
    strongest_flagship_id: str
    router: FlagshipRouter
    protocol: list[str]
    evaluations: list[EvaluationSet]
    suite_matrix: list[LearnedMatrixRow]  # every model over all 600 suite prompts
    spend_usd: dict[str, float]  # provider-billed cost of the flagship runs, per prompt set
    spend_by_model_usd: dict[str, float]  # the same, per flagship, both prompt sets together
