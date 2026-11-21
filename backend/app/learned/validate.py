"""Offline integrity checks for the committed data (week of Nov 26: data validation).

    uv run --project backend python -m app.learned.validate
    uv run --project backend python -m app.learned.validate --data-dir PATH   # another copy

Reads committed files only: it calls no provider and needs no key. Each check prints one line,
PASS or FAIL with a short detail, then a summary; the exit code is 1 if any check failed.

- Each cell table (``learned/cells.jsonl`` and every ``learned/*-cells.jsonl``) matches the
  checksum and row counts in its ``.meta.json``, has one row per (suite, prompt, model), names
  only prompts that exist in its suite file (with the same benchmark, task group, and split),
  and has only the outcome columns: no prompt or response text.
- ``learned/final-evaluation.json`` names the fresh set and the router artifact by their
  checksums, and each evaluation's model matrix (prompts, right answers, failed calls, billed
  cost) is recomputed from ``cells.jsonl``.
- Every ``learned/*-study.json`` gets the same recomputation from ``cells.jsonl`` and the study's
  own cell table, or exactly the tables its ``cell_tables`` list names.
- No file under ``learned/`` or ``registry/`` holds a string that looks like an API key or a
  bearer token. A finding names the file, line, and kind, never the string itself.

Checksums are SHA-256 with CRLF read as LF (as ``final_eval._sha256`` computes them), so a
Windows checkout agrees with the files git stores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from app.config import REPOSITORY_ROOT

DATA_DIR = REPOSITORY_ROOT / "data"
LEARNED = Path("learned")
CELLS_FILE = LEARNED / "cells.jsonl"
FINAL_REPORT_FILE = LEARNED / "final-evaluation.json"
ROUTER_FILE = LEARNED / "cp3-router-model.json"
# Suite name in the cell tables -> its prompt file, and the key of its checksum in the meta.
SUITES = {
    "cp3": (Path("benchmarks") / "cp3_suite.jsonl", "suite_sha256"),
    "final": (Path("benchmarks") / "final_heldout.jsonl", "final_sha256"),
}
# Evaluation id -> (suite, router split of its prompts; None for every prompt in the suite).
EVALUATION_PROMPTS: dict[str, tuple[str, str | None]] = {
    "cp3_test": ("cp3", "test"),
    "final": ("final", None),
}
# Exactly the columns final_eval._cell_row writes: outcomes, no prompt or response text.
CELL_COLUMNS = frozenset({
    "suite", "sample_id", "benchmark", "task_group", "router_split", "model_id", "status",
    "correct", "latency_ms", "cost_usd", "completion_tokens",
})
SUITE_FIELDS = ("benchmark", "task_group", "router_split")
SCANNED_DIRS = (LEARNED, Path("registry"))
SECRET_PATTERNS = {
    "OpenRouter key prefix": re.compile(r"sk-or-"),
    "Google API key prefix": re.compile(r"AIza"),
    "NVIDIA key prefix": re.compile(r"nvapi-"),
    "bearer token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
}
# A long unbroken run of letters and digits mixing upper case, lower case, and digits looks like
# a token; hex digests (lower case only) and hyphenated identifiers do not match.
LONG_RUN = re.compile(r"[A-Za-z0-9]{32,}")
COST_TOLERANCE = 1.5e-6  # the matrix stores costs rounded to 6 decimals


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

    def line(self) -> str:
        return f"{'PASS' if self.passed else 'FAIL'}  {self.name}: {self.detail}"


Row = dict[str, Any]
Suites = dict[str, dict[str, Row]]


def lf_sha256(path: Path) -> str:
    """SHA-256 of a committed text file with CRLF read as LF (``final_eval._sha256``)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_jsonl(path: Path) -> list[Row]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"line {number} is not JSON ({error.msg})") from None
            if not isinstance(row, dict):
                raise ValueError(f"line {number} is not a JSON object")
            rows.append(row)
    return rows


def _read_json(path: Path) -> Row:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return data


def _short(digest: object) -> str:
    return f"{str(digest)[:12]}..."


def _summarize(problems: list[str], limit: int = 3) -> str:
    more = f" (+{len(problems) - limit} more)" if len(problems) > limit else ""
    return "; ".join(problems[:limit]) + more


def _guarded(name: str, check: Callable[[], Check]) -> Check:
    """A check that crashes on malformed data fails instead of stopping the run."""
    try:
        return check()
    except Exception as error:  # any crash is a failed check, not a stopped run
        return Check(name, False, f"{type(error).__name__}: {error}")


def _checksum(name: str, path: Path, expected: object, source: str) -> Check:
    actual = lf_sha256(path)
    if expected == actual:
        return Check(name, True, f"{path.name} matches {source} ({_short(actual)})")
    return Check(name, False,
                 f"{source} says {_short(expected)}, {path.name} is {_short(actual)}")


def load_suites(data_dir: Path, checks: list[Check]) -> Suites:
    """Each suite's prompts by sample id; a suite file that cannot be read or does not match its
    meta's checksum is reported."""
    suites: Suites = {}
    for suite, (relative, key) in SUITES.items():
        path = data_dir / relative
        name = relative.as_posix()
        try:
            rows = read_jsonl(path)
            meta = _read_json(path.with_suffix(".meta.json"))
        except (OSError, ValueError) as error:
            checks.append(Check(f"{name} readable", False, str(error)))
            suites[suite] = {}
            continue
        suites[suite] = {str(row.get("sample_id")): row for row in rows}
        checks.append(_guarded(f"{name} checksum", partial(
            _checksum, f"{name} checksum", path, meta.get(key),
            path.with_suffix(".meta.json").name,
        )))
    return suites


def _key(row: Row) -> tuple[str, str, str]:
    return (str(row.get("suite")), str(row.get("sample_id")), str(row.get("model_id")))


def _row_counts(name: str, rows: list[Row], meta: Row) -> Check:
    problems = []
    if meta.get("rows") != len(rows):
        problems.append(f"meta says {meta.get('rows')} rows, the file has {len(rows)}")
    by_suite = dict(Counter(str(row.get("suite")) for row in rows))
    if meta.get("rows_by_suite") != by_suite:
        problems.append(f"rows by suite: meta {meta.get('rows_by_suite')}, file {by_suite}")
    if "rows_by_model" in meta:
        by_model = dict(Counter(str(row.get("model_id")) for row in rows))
        if meta["rows_by_model"] != by_model:
            problems.append(f"rows by model: meta {meta['rows_by_model']}, file {by_model}")
    if problems:
        return Check(name, False, _summarize(problems))
    counts = ", ".join(f"{suite} {count}" for suite, count in sorted(by_suite.items()))
    return Check(name, True, f"{len(rows)} rows as the meta says ({counts})")


def _unique(name: str, rows: list[Row]) -> Check:
    repeated = [key for key, count in Counter(_key(row) for row in rows).items() if count > 1]
    if repeated:
        return Check(name, False, f"{len(repeated)} (suite, sample_id, model_id) keys repeat, "
                                  f"for example {repeated[0]}")
    return Check(name, True, f"{len(rows)} distinct (suite, sample_id, model_id) keys")


def _in_suites(name: str, rows: list[Row], suites: Suites) -> Check:
    problems = []
    for number, row in enumerate(rows, start=1):
        suite = str(row.get("suite"))
        if suite not in suites:
            problems.append(f"row {number}: unknown suite {suite!r}")
            continue
        item = suites[suite].get(str(row.get("sample_id")))
        if item is None:
            problems.append(f"row {number}: {row.get('sample_id')} is not in the {suite} suite")
            continue
        differ = [field for field in SUITE_FIELDS if row.get(field) != item.get(field)]
        if differ:
            problems.append(f"row {number}: {', '.join(differ)} differ from the {suite} suite")
    if problems:
        return Check(name, False, f"{len(problems)} rows: " + _summarize(problems))
    used = sorted({str(row.get("suite")) for row in rows})
    files = " and ".join(SUITES[suite][0].name for suite in used)
    return Check(name, True, f"every sample_id is in {files}, with the same benchmark, "
                             "task group, and split")


def _columns(name: str, rows: list[Row]) -> Check:
    problems = []
    for number, row in enumerate(rows, start=1):
        extra, missing = sorted(set(row) - CELL_COLUMNS), sorted(CELL_COLUMNS - set(row))
        if extra or missing:
            problems.append(f"row {number}: " + ", ".join(
                part for part in (f"extra {extra}" if extra else "",
                                  f"missing {missing}" if missing else "") if part
            ))
    if problems:
        return Check(name, False, f"{len(problems)} rows: " + _summarize(problems))
    return Check(name, True, f"only the {len(CELL_COLUMNS)} outcome columns (no prompt or "
                             "response text)")


def check_cell_table(
    data_dir: Path, path: Path, suites: Suites, checks: list[Check]
) -> list[Row] | None:
    """The table's own checks; returns its rows, or None if it cannot be read."""
    name = path.relative_to(data_dir).as_posix()
    meta_path = path.with_suffix(".meta.json")
    try:
        rows = read_jsonl(path)
        meta = _read_json(meta_path)
    except (OSError, ValueError) as error:
        checks.append(Check(f"{name} readable", False, str(error)))
        return None
    checks.append(_guarded(f"{name} checksum", lambda: _checksum(
        f"{name} checksum", path, meta.get("cells_sha256"), meta_path.name)))
    checks.append(_guarded(f"{name} row counts",
                           lambda: _row_counts(f"{name} row counts", rows, meta)))
    checks.append(_guarded(f"{name} unique cells", lambda: _unique(f"{name} unique cells",
                                                                   rows)))
    checks.append(_guarded(f"{name} prompts", lambda: _in_suites(f"{name} prompts", rows,
                                                                 suites)))
    checks.append(_guarded(f"{name} columns", lambda: _columns(f"{name} columns", rows)))
    return rows


def _matrix(name: str, evaluation: Row, cells: list[Row], suites: Suites, source: str) -> Check:
    """One evaluation's model matrix against a recomputation from the cells over its prompts."""
    evaluation_id = str(evaluation.get("evaluation_id"))
    if evaluation_id not in EVALUATION_PROMPTS:
        return Check(name, False, f"no rule for which prompts evaluation {evaluation_id!r} uses")
    suite, split = EVALUATION_PROMPTS[evaluation_id]
    prompts = {
        sample for sample, item in suites[suite].items()
        if split is None or item.get("router_split") == split
    }
    models = [str(model) for model in evaluation["models"]]
    totals = {model: [0, 0, 0] for model in models}  # prompts, correct, failed calls
    billed = dict.fromkeys(models, 0.0)
    for row in cells:
        model = str(row.get("model_id"))
        if row.get("suite") == suite and row.get("sample_id") in prompts and model in totals:
            totals[model][0] += 1
            totals[model][1] += bool(row["correct"])
            totals[model][2] += row["status"] != "success"
            billed[model] += float(row["cost_usd"])
    problems = []
    if evaluation.get("prompts") != len(prompts):
        problems.append(f"reports {evaluation.get('prompts')} prompts, the suite gives "
                        f"{len(prompts)}")
    reported = {str(row["model_id"]): row for row in evaluation["matrix"]}
    if set(reported) != set(models):
        problems.append(f"matrix models differ from the evaluation's: "
                        f"{sorted(set(reported) ^ set(models))}")
    for model in models:
        entry = reported.get(model)
        if entry is None:
            continue
        for field, mine in zip(("prompts", "correct", "failed_calls"), totals[model],
                               strict=True):
            if entry.get(field) != mine:
                problems.append(f"{model} {field}: reported {entry.get(field)}, cells give "
                                f"{mine}")
        if abs(float(entry["cost_usd"]) - round(billed[model], 6)) > COST_TOLERANCE:
            problems.append(f"{model} cost: reported ${entry['cost_usd']}, cells give "
                            f"${round(billed[model], 6)}")
    if problems:
        return Check(name, False, _summarize(problems))
    return Check(name, True, f"{len(models)} models x {len(prompts)} prompts: prompts, right "
                             f"answers, failed calls, and billed cost recomputed from {source}")


def check_matrices(
    label: str, report: Row, cells: list[Row], suites: Suites, source: str
) -> list[Check]:
    evaluations = report.get("evaluations")
    if not isinstance(evaluations, list) or not evaluations:
        return [Check(f"{label} evaluations", False, "the report lists no evaluations")]
    checks = []
    for evaluation in evaluations:
        name = f"{label} {evaluation.get('evaluation_id')} matrix"
        checks.append(_guarded(name, partial(_matrix, name, evaluation, cells, suites, source)))
    return checks


def check_final_report(
    data_dir: Path, cells: list[Row] | None, suites: Suites, checks: list[Check]
) -> None:
    label = FINAL_REPORT_FILE.as_posix()
    try:
        report = _read_json(data_dir / FINAL_REPORT_FILE)
    except (OSError, ValueError) as error:
        checks.append(Check(f"{label} readable", False, str(error)))
        return
    final_set = data_dir / SUITES["final"][0]
    checks.append(_guarded(f"{label} fresh-set checksum", lambda: _checksum(
        f"{label} fresh-set checksum", final_set, report.get("final_set_sha256"),
        "the report")))
    checks.append(_guarded(f"{label} router checksum", lambda: _checksum(
        f"{label} router checksum", data_dir / ROUTER_FILE, report.get("artifact_sha256"),
        "the report")))
    if cells is None:
        checks.append(Check(f"{label} matrices", False, f"{CELLS_FILE.name} could not be read"))
        return
    checks.extend(check_matrices(label, report, cells, suites, CELLS_FILE.name))


def study_tables(data_dir: Path, study: Path, report: Row) -> list[Path]:
    """The cell tables a study was computed from: its ``cell_tables`` list if it has one (each
    entry relative to the study's folder, or to the repository root), otherwise ``cells.jsonl``
    and ``<prefix>-cells.jsonl``."""
    listed = report.get("cell_tables")
    if listed is None:
        prefix = study.name.removesuffix("-study.json")
        return [data_dir / CELLS_FILE, study.parent / f"{prefix}-cells.jsonl"]
    if not isinstance(listed, list):
        raise ValueError("cell_tables is not a list")
    tables = []
    for entry in listed:
        beside, from_root = study.parent / str(entry), data_dir.parent / str(entry)
        tables.append(beside if beside.exists() or not from_root.exists() else from_root)
    return tables


def check_study(
    data_dir: Path, study: Path, loaded: dict[Path, list[Row] | None], suites: Suites,
    checks: list[Check],
) -> None:
    label = study.relative_to(data_dir).as_posix()
    try:
        report = _read_json(study)
        tables = study_tables(data_dir, study, report)
    except (OSError, ValueError) as error:
        checks.append(Check(f"{label} readable", False, str(error)))
        return
    names = " + ".join(table.name for table in tables)
    missing = [table.name for table in tables if not table.exists()]
    if missing:
        checks.append(Check(f"{label} cell tables", False, f"missing {', '.join(missing)}"))
        return
    cells: list[Row] = []
    for table in tables:
        rows = loaded.get(table.resolve())
        if rows is None:
            try:
                rows = read_jsonl(table)
            except (OSError, ValueError) as error:
                checks.append(Check(f"{label} cell tables", False, f"{table.name}: {error}"))
                return
        cells.extend(rows)
    repeated = sum(count > 1 for count in Counter(_key(row) for row in cells).values())
    if repeated:
        checks.append(Check(f"{label} cell tables", False,
                            f"{repeated} cells appear more than once across {names}"))
        return
    checks.append(Check(f"{label} cell tables", True, f"{names}, no cell repeated"))
    checks.extend(check_matrices(label, report, cells, suites, names))


def _secret_findings(path: Path) -> Iterable[tuple[int, str]]:
    text = path.read_bytes().decode("utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                yield number, kind
        for run in LONG_RUN.findall(line):
            if any(c.isupper() for c in run) and any(c.islower() for c in run) and any(
                c.isdigit() for c in run
            ):
                yield number, "long mixed-case token"
                break


def check_secrets(data_dir: Path, folder: Path) -> Check:
    name = f"{folder.as_posix()}/ secrets"
    files = sorted(path for path in (data_dir / folder).rglob("*") if path.is_file())
    if not files:
        return Check(name, False, "no files found to scan")
    findings = [
        f"{path.relative_to(data_dir).as_posix()} line {number} ({kind})"
        for path in files
        for number, kind in _secret_findings(path)
    ]
    if findings:
        return Check(name, False, f"{len(findings)} secret-looking strings: "
                                  + _summarize(findings))
    return Check(name, True, f"{len(files)} files scanned, nothing that looks like a key or token")


def run(data_dir: Path = DATA_DIR) -> list[Check]:
    checks: list[Check] = []
    suites = load_suites(data_dir, checks)
    learned = data_dir / LEARNED
    tables = sorted({learned / CELLS_FILE.name, *learned.glob("*-cells.jsonl")})
    loaded = {
        table.resolve(): check_cell_table(data_dir, table, suites, checks) for table in tables
    }
    check_final_report(data_dir, loaded[(data_dir / CELLS_FILE).resolve()], suites, checks)
    for study in sorted(learned.glob("*-study.json")):
        check_study(data_dir, study, loaded, suites, checks)
    checks.extend(
        _guarded(f"{folder.as_posix()}/ secrets", partial(check_secrets, data_dir, folder))
        for folder in SCANNED_DIRS
    )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="The data directory to check (default: the repository's data/)")
    args = parser.parse_args(argv)
    checks = run(args.data_dir)
    for check in checks:
        print(check.line())
    failed = sum(not check.passed for check in checks)
    print(f"{len(checks)} checks: {len(checks) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
