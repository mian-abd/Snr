"""Prompt and model features for P(success | prompt, model) (proposal, "Routing Strategies").

The proposal's feature set: task group, prompt length, simple structural features, expected
output length, model identity, model cost, recent measured latency, and historical success.
Model history (success rate, latency, output length) is computed from the history splits only
(training rows by default). For a row from those splits it excludes that row's own prompt
(leave-one-prompt-out), so a model's historical success never contains the label it predicts.

Benchmark prompts carry their task group and answer options. A live prompt does not, so
``infer_task_group`` and ``count_options`` recover them from the text.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Any

from app.benchmarks.suite import RouterSplit, SuiteItem, TaskGroup
from app.registry.pool import PoolModel
from app.routing.policy import effort_score, prompt_signals

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")
OPTION_RE = re.compile(r"^\s*\(?([A-J])[.)]\s+\S", re.MULTILINE)


@dataclass(frozen=True)
class Cell:
    """One prompt-model outcome from the benchmark matrix."""

    sample_id: str
    model_id: str
    task_group: TaskGroup
    router_split: RouterSplit
    correct: bool
    served: bool
    latency_ms: float
    completion_tokens: int | None
    cost_usd: float


def infer_task_group(text: str) -> TaskGroup:
    """Guess a live prompt's task group from the rule router's visible signals."""
    signals = prompt_signals(text)
    if "code" in signals or "def " in text:
        return TaskGroup.CODE
    if "math" in signals and count_options(text) == 0:
        return TaskGroup.MATH
    return TaskGroup.QA


def count_options(text: str) -> int:
    """Count lettered answer options ("A. ..." or "(B) ...") on their own lines."""
    return len(set(OPTION_RE.findall(text)))


def text_features(text: str, group: TaskGroup, option_count: int) -> dict[str, float]:
    signals = prompt_signals(text)
    lines = text.count("\n") + 1
    return {
        "task_math": float(group == TaskGroup.MATH),
        "task_qa": float(group == TaskGroup.QA),
        "task_code": float(group == TaskGroup.CODE),
        "log_chars": math.log1p(len(text)),
        "log_words": math.log1p(len(text.split())),
        "log_numbers": math.log1p(len(NUMBER_RE.findall(text))),
        "log_lines": math.log1p(lines),
        "log_sentences": math.log1p(len(SENTENCE_RE.findall(text))),
        "option_count": float(option_count),
        "has_function_signature": float("def " in text),
        "has_docstring_examples": float(">>>" in text or "assert " in text),
        "signal_math": float("math" in signals),
        "signal_code": float("code" in signals),
        "signal_long": float("long_prompt" in signals),
        "signal_many_numbers": float("many_numbers" in signals),
        "effort_score": float(effort_score(signals)),
    }


def prompt_features(item: SuiteItem) -> dict[str, float]:
    return text_features(item.question, item.task_group, len(item.options))


class ModelHistory:
    """Per-model, per-task statistics from the history splits, with leave-one-prompt-out lookups."""

    def __init__(
        self, cells: list[Cell], splits: frozenset[RouterSplit] = frozenset({RouterSplit.TRAIN})
    ) -> None:
        self.splits = splits
        self.counts: dict[tuple[str, TaskGroup], list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.outcomes: dict[tuple[str, str], float] = {}
        latency: dict[str, list[float]] = defaultdict(list)
        tokens: dict[tuple[str, TaskGroup], list[int]] = defaultdict(list)
        for cell in cells:
            if cell.router_split not in splits:
                continue
            tally = self.counts[(cell.model_id, cell.task_group)]
            tally[0] += float(cell.correct)
            tally[1] += 1.0
            self.outcomes[(cell.model_id, cell.sample_id)] = float(cell.correct)
            if cell.served:
                latency[cell.model_id].append(cell.latency_ms)
                if cell.completion_tokens is not None:
                    tokens[(cell.model_id, cell.task_group)].append(cell.completion_tokens)
        self.latency_ms = {model: median(values) for model, values in latency.items()}
        self.output_tokens = {key: float(median(values)) for key, values in tokens.items()}

    def success_rate(self, model_id: str, group: TaskGroup, exclude_sample: str | None) -> float:
        successes, total = self.counts.get((model_id, group), (0.0, 0.0))
        if exclude_sample is not None and (model_id, exclude_sample) in self.outcomes:
            successes -= self.outcomes[(model_id, exclude_sample)]
            total -= 1.0
        # A weak prior keeps tiny groups from producing exact 0 or 1 rates.
        return (successes + 1.0) / (total + 2.0)

    def snapshot(self) -> dict[str, Any]:
        """The aggregates a live router needs; per-prompt outcomes are left out."""
        return {
            "splits": sorted(split.value for split in self.splits),
            "success_counts": {
                f"{model}|{group.value}": tally for (model, group), tally in self.counts.items()
            },
            "latency_ms": self.latency_ms,
            "output_tokens": {
                f"{model}|{group.value}": value
                for (model, group), value in self.output_tokens.items()
            },
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> ModelHistory:
        history = cls([], frozenset(RouterSplit(split) for split in data["splits"]))
        for key, tally in data["success_counts"].items():
            model, group = key.split("|")
            history.counts[(model, TaskGroup(group))] = [float(tally[0]), float(tally[1])]
        history.latency_ms = {model: float(value) for model, value in data["latency_ms"].items()}
        for key, value in data["output_tokens"].items():
            model, group = key.split("|")
            history.output_tokens[(model, TaskGroup(group))] = float(value)
        return history


def model_features(
    model: PoolModel,
    group: TaskGroup,
    history: ModelHistory,
    pool_ids: list[str],
    *,
    exclude_sample: str | None,
) -> dict[str, float]:
    features = {f"model_{model_id}": float(model.id == model_id) for model_id in pool_ids}
    for model_id in pool_ids:
        # Model-by-task interactions let a linear model learn per-task strengths.
        for task in TaskGroup:
            features[f"model_{model_id}_x_{task.value}"] = float(
                model.id == model_id and group == task
            )
    output_tokens = history.output_tokens.get((model.id, group), 512.0)
    features.update(
        {
            "log_price_in_per_million": math.log1p(float(model.prompt_price_per_token) * 1e6),
            "log_price_out_per_million": math.log1p(float(model.completion_price_per_token) * 1e6),
            "is_local": float(model.access.value == "local"),
            "is_free": float(model.access.value != "paid"),
            "log_latency_ms": math.log1p(history.latency_ms.get(model.id, 5000.0)),
            "log_expected_output_tokens": math.log1p(output_tokens),
            "historical_success": history.success_rate(model.id, group, exclude_sample),
        }
    )
    return features


def feature_row(
    item: SuiteItem,
    model: PoolModel,
    history: ModelHistory,
    pool_ids: list[str],
) -> dict[str, float]:
    exclude = item.sample_id if item.router_split in history.splits else None
    return {
        **prompt_features(item),
        **model_features(model, item.task_group, history, pool_ids, exclude_sample=exclude),
    }
