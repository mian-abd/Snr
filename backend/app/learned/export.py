"""Export experiment results as CSV or JSON (proposal: "The user will be able to export experiment
results as a CSV or JSON file").

    uv run --project backend python -m app.learned.export strategies --format csv --out out.csv

Every table is built from committed files only (the final-evaluation report, the per-prompt
decisions, and the text-free cell table), so the console can serve it and a clone can rebuild it.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any

from app.domain.models import EvaluationSet, FinalEvaluationReport, Interval
from app.domain.scoring_fix import ScoringFixReport
from app.domain.study import PoolStudyReport
from app.learned.studies import ADDED_POOLS, STUDIES
from app.storage import read_jsonl

REPORT_FILE = Path("learned") / "final-evaluation.json"  # relative to the data directory
DECISIONS_FILE = Path("learned") / "final-decisions.jsonl"
CELLS_FILE = Path("learned") / "cells.jsonl"
SCORING_FIX_FILE = Path("learned") / "scoring-fix-study.json"
TABLES = {
    "strategies": "Every strategy and oracle on both evaluations, with 95% intervals",
    "comparisons": "The fixed paired comparisons with McNemar and Holm-adjusted p-values",
    "errors": "Routing errors and oracle gap per preset and task group",
    "robustness": "Every robustness scenario and strategy",
    "sweep": "The user-priority sweep",
    "decisions": "Every strategy's model choice and outcome on every prompt",
    "cells": "Every model's scored outcome on every prompt (no response text)",
    "study_strategies": "Every strategy in each pool study, on both evaluations, with intervals",
    "study_comparisons": "Each pool study's fixed paired comparisons",
    "study_models": "Every model's results in each pool study, per prompt set and task",
    "added_cells": "The added models' scored outcome on every prompt (no response text)",
    "scoring_fix": "The scoring fix: every scenario and strategy for the frozen and fixed scoring",
}
STUDY_TABLES = {"study_strategies", "study_comparisons", "study_models"}


class ExportError(LookupError):
    pass


def _bounds(prefix: str, interval: Interval | None) -> dict[str, float | None]:
    return {
        f"{prefix}_ci_low": None if interval is None else interval.low,
        f"{prefix}_ci_high": None if interval is None else interval.high,
    }


def load_report(data_dir: Path) -> FinalEvaluationReport:
    path = data_dir / REPORT_FILE
    if not path.exists():
        raise ExportError("No final-evaluation report has been generated yet")
    return FinalEvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))


def _studies(data_dir: Path) -> list[PoolStudyReport]:
    reports = []
    for spec in STUDIES.values():
        path = data_dir / "learned" / spec.report_path.name
        if path.exists():
            reports.append(PoolStudyReport.model_validate_json(path.read_text(encoding="utf-8")))
    if not reports:
        raise ExportError("No pool study has been run yet")
    return reports


def _strategy_rows(evaluation: EvaluationSet) -> list[dict[str, Any]]:
    spread = {item.strategy_id: item for item in evaluation.uncertainty}
    rows = []
    for strategy in evaluation.strategies + evaluation.oracle:
        interval = spread.get(strategy.strategy_id)
        row: dict[str, Any] = {
            "evaluation": evaluation.evaluation_id,
            "strategy": strategy.strategy_id,
            "prompts": strategy.prompts,
            "correct": strategy.correct,
            "accuracy": round(strategy.accuracy, 6),
            **_bounds("accuracy", interval.accuracy if interval else None),
            "total_cost_usd": strategy.total_cost_usd,
            **_bounds("total_cost_usd", interval.total_cost_usd if interval else None),
            "cost_per_correct_usd": strategy.cost_per_correct_usd,
            "median_latency_ms": strategy.median_latency_ms,
            **_bounds("median_latency_ms", interval.median_latency_ms if interval else None),
            "p95_latency_ms": strategy.p95_latency_ms,
            "selected_models": "; ".join(
                f"{model} x{count}" for model, count in strategy.selected_models.items()
            ),
        }
        for task, outcome in strategy.by_task.items():
            row[f"{task}_correct"] = outcome.correct
            row[f"{task}_prompts"] = outcome.prompts
            row[f"{task}_cost_usd"] = outcome.total_cost_usd
        rows.append(row)
    return rows


def _comparison_rows(evaluation: EvaluationSet) -> list[dict[str, Any]]:
    rows = []
    for comparison in evaluation.comparisons:
        data = comparison.model_dump(mode="json")
        flat = {key: value for key, value in data.items() if not key.endswith("_ci")}
        for key in ("accuracy_difference", "cost_difference", "cost_ratio",
                    "median_latency_difference"):
            flat.update(_bounds(key, getattr(comparison, f"{key}_ci")))
        rows.append({"evaluation": evaluation.evaluation_id, **flat})
    return rows


def _study_rows(table: str, data_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for study in _studies(data_dir):
        tag = {"study": study.study_id}
        if table == "study_models":
            matrices = [("suite", study.suite_matrix)] + [
                (evaluation.evaluation_id, evaluation.matrix) for evaluation in study.evaluations
            ]
            for prompt_set, matrix in matrices:
                for model in matrix:
                    row: dict[str, Any] = {
                        **tag,
                        "prompt_set": prompt_set,
                        "model": model.model_id,
                        "added_from": study.added_from.get(model.model_id, "base"),
                        "access": model.access,
                        "prompts": model.prompts,
                        "correct": model.correct,
                        "failed_calls": model.failed_calls,
                        "cost_usd": model.cost_usd,
                        "median_latency_ms": model.median_latency_ms,
                    }
                    for task, prompts in model.prompts_by_task.items():
                        row[f"{task}_correct"] = model.correct_by_task.get(task, 0)
                        row[f"{task}_prompts"] = prompts
                    rows.append(row)
            continue
        for evaluation in study.evaluations:
            source = (_strategy_rows if table == "study_strategies" else _comparison_rows)
            rows.extend({**tag, **row} for row in source(evaluation))
    return rows


def _scoring_fix_rows(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / SCORING_FIX_FILE
    if not path.exists():
        raise ExportError("The scoring-fix study has not been run yet")
    report = ScoringFixReport.model_validate_json(path.read_text(encoding="utf-8"))
    rows = []
    for evaluation in report.evaluations:
        for scoring, robustness in (("frozen", evaluation.frozen), ("fixed", evaluation.fixed)):
            for scenario in robustness.scenarios:
                for entry in scenario.strategies:
                    rows.append({
                        "evaluation": evaluation.evaluation_id,
                        "scoring": scoring,
                        "scenario": scenario.scenario.scenario_id,
                        "title": scenario.scenario.title,
                        "observed": scenario.scenario.observed,
                        "strategy": entry.strategy_id,
                        "prompts": scenario.prompts,
                        "correct": entry.correct,
                        "total_cost_usd": entry.total_cost_usd,
                        "median_latency_ms": entry.median_latency_ms,
                        "changed_decisions": entry.changed_decisions,
                        "selected_models": "; ".join(
                            f"{model} x{count}" for model, count in entry.selected_models.items()
                        ),
                    })
    return rows


def table_rows(table: str, data_dir: Path) -> list[dict[str, Any]]:
    if table not in TABLES:
        raise ExportError(f"Unknown table {table!r}; choose one of {', '.join(TABLES)}")
    if table == "scoring_fix":
        return _scoring_fix_rows(data_dir)
    if table == "decisions":
        return list(read_jsonl(data_dir / DECISIONS_FILE))
    if table == "cells":
        return list(read_jsonl(data_dir / CELLS_FILE))
    if table == "added_cells":
        added = [
            {"pool": pool.name, **row}
            for pool in ADDED_POOLS.values()
            if (data_dir / "learned" / pool.cells_path.name).exists()
            for row in read_jsonl(data_dir / "learned" / pool.cells_path.name)
        ]
        if not added:
            raise ExportError("No added models have been run yet")
        return added
    if table in STUDY_TABLES:
        return _study_rows(table, data_dir)
    report = load_report(data_dir)
    rows: list[dict[str, Any]] = []
    for evaluation in report.evaluations:
        if table == "strategies":
            rows.extend(_strategy_rows(evaluation))
        elif table == "comparisons":
            rows.extend(_comparison_rows(evaluation))
        elif table == "errors":
            for analysis in evaluation.routing_errors:
                for task, breakdown in [("all", analysis.overall), *analysis.by_task.items()]:
                    rows.append({
                        "evaluation": evaluation.evaluation_id,
                        "strategy": analysis.strategy_id,
                        "task_group": task,
                        **breakdown.model_dump(mode="json"),
                    })
    if table == "robustness":
        for result in report.robustness:
            for scenario in result.scenarios:
                for entry in scenario.strategies:
                    rows.append({
                        "evaluation": result.evaluation_id,
                        "scenario": scenario.scenario.scenario_id,
                        "title": scenario.scenario.title,
                        "condition": scenario.scenario.condition,
                        "observed": scenario.scenario.observed,
                        "strategy": entry.strategy_id,
                        "prompts": scenario.prompts,
                        "correct": entry.correct,
                        "accuracy": round(entry.accuracy, 6),
                        "total_cost_usd": entry.total_cost_usd,
                        "median_latency_ms": entry.median_latency_ms,
                        "changed_decisions": entry.changed_decisions,
                        "selected_models": "; ".join(
                            f"{model} x{count}"
                            for model, count in entry.selected_models.items()
                        ),
                    })
    if table == "sweep":
        for result in report.robustness:
            for point in result.priority_sweep:
                rows.append({
                    "evaluation": result.evaluation_id,
                    "axis": point.axis,
                    "weight": point.weight,
                    "correct": point.correct,
                    "accuracy": round(point.accuracy, 6),
                    "total_cost_usd": point.total_cost_usd,
                    "median_latency_ms": point.median_latency_ms,
                    "selected_models": "; ".join(
                        f"{model} x{count}" for model, count in point.selected_models.items()
                    ),
                })
    return rows


def to_csv(rows: list[dict[str, Any]]) -> str:
    columns: list[str] = []
    for row in rows:
        columns.extend(key for key in row if key not in columns)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def render(table: str, fmt: str, data_dir: Path) -> tuple[str, str]:
    """The table as text and its media type."""
    rows = table_rows(table, data_dir)
    if fmt == "csv":
        return to_csv(rows), "text/csv; charset=utf-8"
    if fmt == "json":
        return json.dumps(rows, indent=1) + "\n", "application/json"
    raise ExportError("format must be csv or json")


def main() -> int:
    from app.config import REPOSITORY_ROOT

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("table", choices=sorted(TABLES))
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    text, _ = render(args.table, args.format, REPOSITORY_ROOT / "data")
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
