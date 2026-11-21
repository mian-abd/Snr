"""Pool studies (weeks of Nov 19 and 26): routers refit on the frozen pool plus added models."""

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


class StudyRouter(StrictModel):
    """The study's router: the Checkpoint 3 recipe refit on the widened pool."""

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


class ExcludedModel(StrictModel):
    """A listed model that did not answer every prompt, so no router can be fit with it."""

    model_id: str
    display_name: str
    prompts_scored: int
    prompts_total: int
    spend_usd: float
    reason: str


class PoolStudyReport(StrictModel):
    """Does widening the frozen router's pool with these models pay off?"""

    study_id: str
    title: str
    question: str
    base_snapshot_id: str
    added_snapshot_ids: list[str]
    added: list[PoolModel]  # the listed models that answered every prompt
    added_from: dict[str, str]  # model ID -> added pool name ("flagship", "budget")
    excluded: list[ExcludedModel]
    strongest_added_id: str
    router: StudyRouter
    protocol: list[str]
    evaluations: list[EvaluationSet]
    suite_matrix: list[LearnedMatrixRow]  # every model over all 600 suite prompts
    cell_tables: list[str]  # repository-relative tables the report was built from
    spend_usd: dict[str, float]  # provider-billed cost of the added models' runs, per prompt set
    spend_by_model_usd: dict[str, float]  # the same, per added model, both prompt sets


class StudySummary(StrictModel):
    study_id: str
    title: str
    question: str
    added: int
    pool: str  # the router pool the site offers for this study
