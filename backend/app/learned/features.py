"""Prompt and model features for P(success | prompt, model) (proposal, "Routing Strategies").

The proposal's feature set: task group, prompt length, simple structural features, expected
output length, model identity, model cost, recent measured latency, and historical success.
Model history (success rate, latency, output length) is computed from training-split rows only.
For a training row it excludes that row's own prompt (leave-one-prompt-out), so a model's
historical success never contains the label it is trying to predict.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from app.benchmarks.suite import RouterSplit, SuiteItem, TaskGroup
from app.registry.pool import PoolModel
from app.routing.policy import effort_score, prompt_signals

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")


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


def prompt_features(item: SuiteItem) -> dict[str, float]:
    text = item.question
    signals = prompt_signals(text)
    lines = text.count("\n") + 1
    return {
        "task_math": float(item.task_group == TaskGroup.MATH),
        "task_qa": float(item.task_group == TaskGroup.QA),
        "task_code": float(item.task_group == TaskGroup.CODE),
        "log_chars": math.log1p(len(text)),
        "log_words": math.log1p(len(text.split())),
        "log_numbers": math.log1p(len(NUMBER_RE.findall(text))),
        "log_lines": math.log1p(lines),
        "log_sentences": math.log1p(len(SENTENCE_RE.findall(text))),
        "option_count": float(len(item.options)),
        "has_function_signature": float("def " in text),
        "has_docstring_examples": float(">>>" in text or "assert " in text),
        "signal_math": float("math" in signals),
        "signal_code": float("code" in signals),
        "signal_long": float("long_prompt" in signals),
        "signal_many_numbers": float("many_numbers" in signals),
        "effort_score": float(effort_score(signals)),
    }


class ModelHistory:
    """Per-model, per-task statistics from training rows, with leave-one-prompt-out lookups."""

    def __init__(self, cells: list[Cell]) -> None:
        train = [cell for cell in cells if cell.router_split == RouterSplit.TRAIN]
        self.success: dict[tuple[str, TaskGroup], list[tuple[str, float]]] = defaultdict(list)
        latency: dict[str, list[float]] = defaultdict(list)
        tokens: dict[tuple[str, TaskGroup], list[int]] = defaultdict(list)
        for cell in train:
            self.success[(cell.model_id, cell.task_group)].append(
                (cell.sample_id, float(cell.correct))
            )
            if cell.served:
                latency[cell.model_id].append(cell.latency_ms)
                if cell.completion_tokens is not None:
                    tokens[(cell.model_id, cell.task_group)].append(cell.completion_tokens)
        self.latency_ms = {model: median(values) for model, values in latency.items()}
        self.output_tokens = {key: median(values) for key, values in tokens.items()}

    def success_rate(self, model_id: str, group: TaskGroup, exclude_sample: str | None) -> float:
        rows = [
            value
            for sample_id, value in self.success.get((model_id, group), [])
            if sample_id != exclude_sample
        ]
        # A weak prior keeps tiny groups from producing exact 0 or 1 rates.
        return (sum(rows) + 1.0) / (len(rows) + 2.0)


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
    exclude = item.sample_id if item.router_split == RouterSplit.TRAIN else None
    return {
        **prompt_features(item),
        **model_features(model, item.task_group, history, pool_ids, exclude_sample=exclude),
    }
