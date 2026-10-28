"""The Checkpoint 3 benchmark suite: fixed samples from four benchmarks and a fixed router split.

The suite is built once by ``app.benchmarks.prepare_suite`` and committed. Every model answers
exactly these prompts, and the train / validation / test assignment is fixed before any model
runs, so held-out prompts can never influence router training or tuning.
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from app.domain.models import StrictModel
from app.storage import read_jsonl


class Benchmark(StrEnum):
    GSM8K = "gsm8k"
    MMLU_PRO = "mmlu_pro"
    HUMANEVAL_PLUS = "humaneval_plus"
    MBPP_PLUS = "mbpp_plus"


class TaskGroup(StrEnum):
    MATH = "math"
    QA = "qa"
    CODE = "code"


class RouterSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


TASK_GROUPS = {
    Benchmark.GSM8K: TaskGroup.MATH,
    Benchmark.MMLU_PRO: TaskGroup.QA,
    Benchmark.HUMANEVAL_PLUS: TaskGroup.CODE,
    Benchmark.MBPP_PLUS: TaskGroup.CODE,
}

# Proposal: ~60% training, 20% validation, 20% held-out test.
SPLIT_FRACTIONS = ((RouterSplit.TRAIN, 0.6), (RouterSplit.VALIDATION, 0.2), (RouterSplit.TEST, 0.2))


class SuiteItem(StrictModel):
    """One fixed prompt. Code test suites stay in the pinned source dataset, not in the repo."""

    sample_id: str
    benchmark: Benchmark
    task_group: TaskGroup
    dataset: str
    configuration: str | None = None
    source_split: str
    revision: str
    source_id: str
    category: str | None = None
    question: str
    options: list[str] = Field(default_factory=list)
    expected_answer: str | None = None
    entry_point: str | None = None
    router_split: RouterSplit


def assign_splits(sample_ids: list[str], seed: int) -> dict[str, RouterSplit]:
    """Shuffle deterministically, then cut 60/20/20. Call once per benchmark to stratify."""
    ordered = sorted(sample_ids)
    random.Random(seed).shuffle(ordered)
    total = len(ordered)
    train_end = round(total * SPLIT_FRACTIONS[0][1])
    validation_end = train_end + round(total * SPLIT_FRACTIONS[1][1])
    assignment: dict[str, RouterSplit] = {}
    for position, sample_id in enumerate(ordered):
        if position < train_end:
            assignment[sample_id] = RouterSplit.TRAIN
        elif position < validation_end:
            assignment[sample_id] = RouterSplit.VALIDATION
        else:
            assignment[sample_id] = RouterSplit.TEST
    return assignment


def load_suite(path: Path) -> list[SuiteItem]:
    items = [SuiteItem.model_validate(row) for row in read_jsonl(path)]
    ids = [item.sample_id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Suite sample IDs must be unique")
    for item in items:
        if TASK_GROUPS[item.benchmark] != item.task_group:
            raise ValueError(f"Wrong task group for {item.sample_id}")
    return items


def split_counts(items: list[SuiteItem]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = {}
    for item in items:
        counts.setdefault(item.benchmark.value, Counter())[item.router_split.value] += 1
    return {benchmark: dict(counter) for benchmark, counter in sorted(counts.items())}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
