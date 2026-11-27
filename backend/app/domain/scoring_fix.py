"""The scoring fix, tested (week of Dec 3): the report's typed shape.

``app.learned.scoring_fix`` builds it. These models only describe the file, so the server can
serve it without importing the training stack.
"""

from __future__ import annotations

from pydantic import Field

from app.domain.models import (
    LearnedMatrixRow,
    PairedComparison,
    RobustnessReport,
    RoutingPriority,
    ScenarioStrategy,
    StrictModel,
    WeightTuningResult,
)
from app.learned.router import ScoringReference


class ScoringFixTuning(StrictModel):
    """How the fixed variant's presets were chosen: on the Checkpoint 3 validation split only."""

    classifier: str  # the frozen router's artifact, refit on the training split alone
    validation_prompts: int
    reliability_floor: float
    reliability_grid: list[float]
    tuning_reference: ScoringReference  # divisors used while tuning (training-split estimates)
    frozen_recipe_reproduced: bool  # the old recipe, rerun here, gives the frozen presets
    recipe_check_presets: list[WeightTuningResult]  # the old recipe rerun, to check it
    reference_only_presets: list[WeightTuningResult]  # fixed divisors, reliability grid kept
    fixed_presets: list[WeightTuningResult]  # fixed divisors and the floored reliability grid
    note: str


class EvidenceRow(StrictModel):
    """One router and priority in one scenario: told about the change, then with old estimates."""

    evaluation_id: str
    scenario_id: str
    priority: RoutingPriority
    router: str  # "frozen" or "fixed"
    told: ScenarioStrategy
    old: ScenarioStrategy
    unchanged: ScenarioStrategy  # the same router and priority with nothing changed
    told_vs_old_p: float | None = None  # McNemar on right answers, Holm-adjusted


class QuestionAnswer(StrictModel):
    question_id: str
    question: str
    rule: str  # how "yes" was decided, fixed in code before the results were read
    holds_fresh: bool
    holds_test: bool
    answer_fresh: str  # the numbers behind the verdict on the fresh prompts
    answer_test: str  # and on the Checkpoint 3 test split
    evidence: list[EvidenceRow]


class ScoringFixEvaluation(StrictModel):
    evaluation_id: str  # "cp3_test" or "final"
    title: str
    description: str
    prompts: int
    models: list[str]
    matrix: list[LearnedMatrixRow]
    comparisons: list[PairedComparison]  # fixed questions' paired tests, Holm-adjusted together
    frozen: RobustnessReport  # the frozen router, every scenario
    fixed: RobustnessReport  # the fixed variant, every scenario


class ScoringFixReport(StrictModel):
    """The frozen router and a variant with fixed cost and time references and a small default
    reliability weight, on the same prompts and scenarios."""

    study_id: str
    title: str
    artifact_id: str
    artifact_sha256: str
    final_set_sha256: str
    pool_snapshot_id: str
    reference: ScoringReference  # divisors the fixed variant uses (the frozen estimates' maxima)
    frozen_weights: dict[RoutingPriority, dict[str, float]]
    fixed_weights: dict[RoutingPriority, dict[str, float]]
    tuning: ScoringFixTuning
    protocol: list[str]
    caveats: list[str]
    questions: list[QuestionAnswer]
    evaluations: list[ScoringFixEvaluation]
    cell_tables: list[str] = Field(default_factory=list)
