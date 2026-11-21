"""The prompt explorer: every prompt of an evaluation, every model's outcome, every choice.

Built from committed files only, so nothing here calls a model: the prompt sets under
``data/benchmarks``, the text-free cell tables (the frozen pool's ``cells.jsonl`` and each added
pool's, skipped while missing), and the per-prompt decisions of the final evaluation. A model
appears only if it answered every prompt of the evaluation; a model an added pool lists as
stopped is left out.

The assembled table is cached per data directory and evaluation, and rebuilt when any of its
source files changes (for example when an added pool's cell table lands).
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.benchmarks.suite import Benchmark, RouterSplit, SuiteItem, load_suite
from app.domain.explorer import (
    ExplorerEvaluation,
    ExplorerModel,
    ExplorerPrompt,
    PromptExplorer,
    PromptOutcome,
)
from app.domain.models import GenerationStatus
from app.learned.export import CELLS_FILE, DECISIONS_FILE
from app.learned.router import ROUTER_POOL_FILE
from app.learned.studies import ADDED_POOLS
from app.registry.pool import PoolModel, load_pool
from app.storage import read_jsonl

# Per evaluation: the prompt file (under the data directory), its rows, and the cells' suite.
SOURCES: dict[ExplorerEvaluation, tuple[Path, RouterSplit, str]] = {
    ExplorerEvaluation.FINAL: (Path("benchmarks/final_heldout.jsonl"), RouterSplit.FINAL, "final"),
    ExplorerEvaluation.CP3_TEST: (Path("benchmarks/cp3_suite.jsonl"), RouterSplit.TEST, "cp3"),
}
CODE_BENCHMARKS = {Benchmark.HUMANEVAL_PLUS: "HumanEval+", Benchmark.MBPP_PLUS: "MBPP+"}
COST_DIGITS = 7  # billed cost in USD; the smallest calls cost a few millionths of a dollar


class ExplorerError(LookupError):
    pass


def _answer_note(item: SuiteItem) -> str | None:
    label = CODE_BENCHMARKS.get(item.benchmark)
    if label is None:
        return None
    return (
        f"No single right answer: a solution is right when it passes every {label} test for "
        f"{item.entry_point} ({item.dataset}, {item.revision}). The tests stay in that release "
        "and are not stored here."
    )


def _outcome(row: dict[str, Any]) -> PromptOutcome:
    status = GenerationStatus(row["status"])
    return PromptOutcome(
        status=status,
        correct=bool(row["correct"]) and status == GenerationStatus.SUCCESS,
        latency_ms=round(float(row["latency_ms"])),
        cost_usd=round(float(row["cost_usd"]), COST_DIGITS),
    )


def _view(model_id: str, listed: dict[str, PoolModel], added_from: str | None) -> ExplorerModel:
    model = listed.get(model_id)
    return ExplorerModel(
        model_id=model_id,
        display_name=model.display_name if model else model_id,
        access=model.access.value if model else None,
        added_from=added_from,
    )


def assemble(data_dir: Path, evaluation: ExplorerEvaluation) -> PromptExplorer:
    """Read the committed files and join them per prompt (uncached; see ``build_explorer``)."""
    prompt_file, split, suite = SOURCES[evaluation]
    if not (data_dir / prompt_file).exists():
        raise ExplorerError(f"The prompt set for {evaluation.value!r} is not in this checkout")
    items = [item for item in load_suite(data_dir / prompt_file) if item.router_split == split]
    wanted = {item.sample_id for item in items}

    # Where each model is listed (for its name and access) and which table its cells come from.
    listed: dict[str, PoolModel] = {}
    order: list[str] = []
    base_registry = data_dir / ROUTER_POOL_FILE
    if base_registry.exists():
        for model in load_pool(base_registry).models:
            listed.setdefault(model.id, model)
            order.append(model.id)
    tables: list[tuple[Path, str | None]] = [(data_dir / CELLS_FILE, None)]
    stopped: set[str] = set()
    for pool in ADDED_POOLS.values():
        table = data_dir / "learned" / pool.cells_path.name
        if not table.exists():
            continue  # this pool's models have not been run yet
        tables.append((table, pool.name))
        stopped.update(pool.stopped)
        registry = data_dir / "registry" / pool.registry_file
        if registry.exists():
            for model in load_pool(registry).models:
                listed.setdefault(model.id, model)
                order.append(model.id)

    outcomes: dict[str, dict[str, PromptOutcome]] = defaultdict(dict)  # model -> sample -> call
    source: dict[str, str | None] = {}
    for table, pool_name in tables:
        for row in read_jsonl(table):
            if row["suite"] != suite or row["sample_id"] not in wanted:
                continue
            outcomes[row["model_id"]][row["sample_id"]] = _outcome(row)
            source.setdefault(row["model_id"], pool_name)

    rank = {model_id: index for index, model_id in enumerate(order)}
    seen = sorted(outcomes, key=lambda model_id: (rank.get(model_id, len(rank)), model_id))
    shown = [
        model_id for model_id in seen
        if model_id not in stopped and len(outcomes[model_id]) == len(wanted)
    ]
    left_out = [model_id for model_id in seen if model_id not in shown]

    choices: dict[str, dict[str, str]] = defaultdict(dict)  # sample -> strategy -> model
    strategies: list[str] = []
    for row in read_jsonl(data_dir / DECISIONS_FILE):
        if row["evaluation"] != evaluation.value or row["sample_id"] not in wanted:
            continue
        if row["strategy"] not in strategies:
            strategies.append(row["strategy"])
        choices[row["sample_id"]][row["strategy"]] = row["model_id"]

    return PromptExplorer(
        evaluation=evaluation,
        models=[_view(model_id, listed, source[model_id]) for model_id in shown],
        excluded=[_view(model_id, listed, source[model_id]) for model_id in left_out],
        strategies=strategies,
        prompts=[
            ExplorerPrompt(
                sample_id=item.sample_id,
                benchmark=item.benchmark.value,
                task_group=item.task_group,
                category=item.category,
                dataset=item.dataset,
                source_id=item.source_id,
                question=item.question,
                options=item.options,
                expected_answer=item.expected_answer,
                answer_note=_answer_note(item),
                outcomes={model_id: outcomes[model_id][item.sample_id] for model_id in shown},
                choices=choices.get(item.sample_id, {}),
            )
            for item in items
        ],
    )


def _sources(data_dir: Path, evaluation: ExplorerEvaluation) -> list[Path]:
    paths = [
        data_dir / SOURCES[evaluation][0],
        data_dir / CELLS_FILE,
        data_dir / DECISIONS_FILE,
        data_dir / ROUTER_POOL_FILE,
    ]
    for pool in ADDED_POOLS.values():
        paths.append(data_dir / "learned" / pool.cells_path.name)
        paths.append(data_dir / "registry" / pool.registry_file)
    return paths


def _signature(paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
    """Each file's modification time and size (or -1 while missing), to tell when to rebuild."""
    marks = []
    for path in paths:
        try:
            stat = path.stat()
        except FileNotFoundError:
            marks.append((str(path), -1, -1))
        else:
            marks.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(marks)


@lru_cache(maxsize=8)
def _cached(
    data_dir: Path, evaluation: ExplorerEvaluation, signature: tuple[tuple[str, int, int], ...]
) -> PromptExplorer:
    return assemble(data_dir, evaluation)


def build_explorer(data_dir: Path, evaluation: ExplorerEvaluation) -> PromptExplorer:
    """The explorer table, from the cache unless a source file changed since it was built."""
    return _cached(data_dir, evaluation, _signature(_sources(data_dir, evaluation)))
