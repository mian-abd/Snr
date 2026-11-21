"""The prompt explorer: every prompt of an evaluation, how each model did, and who chose what."""

from __future__ import annotations

from enum import StrEnum

from app.domain.models import GenerationStatus, StrictModel, TaskGroup


class ExplorerEvaluation(StrEnum):
    CP3_TEST = "cp3_test"  # the 120 test-split prompts of the Checkpoint 3 suite
    FINAL = "final"  # the 300 fresh prompts


class PromptOutcome(StrictModel):
    """One model's scored call on one prompt. A failed call counts as wrong."""

    status: GenerationStatus
    correct: bool
    latency_ms: int
    cost_usd: float


class ExplorerModel(StrictModel):
    model_id: str
    display_name: str
    access: str | None  # "paid", "free", or "local"; None when no registry lists the model
    added_from: str | None  # the added pool ("flagship", "budget"); None for the frozen pool


class ExplorerPrompt(StrictModel):
    sample_id: str
    benchmark: str
    task_group: TaskGroup
    category: str | None  # MMLU-Pro subject
    dataset: str
    source_id: str
    question: str
    options: list[str]  # MMLU-Pro answer options, A first; empty otherwise
    expected_answer: str | None  # the number for GSM8K, the option letter for MMLU-Pro
    answer_note: str | None  # how a code answer is graded (its tests are not stored here)
    outcomes: dict[str, PromptOutcome]  # model ID -> its scored call
    choices: dict[str, str]  # strategy ID -> the model it chose


class PromptExplorer(StrictModel):
    """Every prompt of one evaluation, with each model's outcome and each strategy's choice."""

    evaluation: ExplorerEvaluation
    models: list[ExplorerModel]  # the models that answered every prompt, in pool order
    excluded: list[ExplorerModel]  # models that answered some of these prompts but not all
    strategies: list[str]  # the strategies with a choice per prompt
    prompts: list[ExplorerPrompt]
