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

from app.domain.models import FinalEvaluationReport, Interval
from app.storage import read_jsonl

REPORT_FILE = Path("learned") / "final-evaluation.json"  # relative to the data directory
DECISIONS_FILE = Path("learned") / "final-decisions.jsonl"
CELLS_FILE = Path("learned") / "cells.jsonl"
TABLES = {
    "strategies": "Every strategy and oracle on both evaluations, with 95% intervals",
    "comparisons": "The fixed paired comparisons with McNemar and Holm-adjusted p-values",
    "errors": "Routing errors and oracle gap per preset and task group",
    "robustness": "Every robustness scenario and strategy",
    "sweep": "The user-priority sweep",
    "decisions": "Every strategy's model choice and outcome on every prompt",
    "cells": "Every model's scored outcome on every prompt (no response text)",
}


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


def table_rows(table: str, data_dir: Path) -> list[dict[str, Any]]:
    if table not in TABLES:
        raise ExportError(f"Unknown table {table!r}; choose one of {', '.join(TABLES)}")
    if table == "decisions":
        return list(read_jsonl(data_dir / DECISIONS_FILE))
    if table == "cells":
        return list(read_jsonl(data_dir / CELLS_FILE))
    report = load_report(data_dir)
    rows: list[dict[str, Any]] = []
    for evaluation in report.evaluations:
        spread = {item.strategy_id: item for item in evaluation.uncertainty}
        if table == "strategies":
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
                    **_bounds("median_latency_ms",
                              interval.median_latency_ms if interval else None),
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
        elif table == "comparisons":
            for comparison in evaluation.comparisons:
                data = comparison.model_dump(mode="json")
                flat = {key: value for key, value in data.items() if not key.endswith("_ci")}
                for key in ("accuracy_difference", "cost_difference", "cost_ratio",
                            "median_latency_difference"):
                    flat.update(_bounds(key, getattr(comparison, f"{key}_ci")))
                rows.append({"evaluation": evaluation.evaluation_id, **flat})
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
