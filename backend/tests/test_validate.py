import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from app.config import REPOSITORY_ROOT
from app.learned import validate
from app.learned.final_eval import _sha256

DATA = REPOSITORY_ROOT / "data"


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    """The committed files the checks read, copied so a test can damage them."""
    copy = tmp_path / "data"
    for folder in ("benchmarks", "learned", "registry"):
        shutil.copytree(DATA / folder, copy / folder)
    return copy


def _failed(data_dir: Path) -> list[str]:
    return [check.name for check in validate.run(data_dir) if not check.passed]


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_committed_data_passes_every_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert validate.main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert all(line.startswith("PASS  ") for line in lines[:-1])
    assert lines[-1] == f"{len(lines) - 1} checks: {len(lines) - 1} passed, 0 failed"
    names = {check.name for check in validate.run()}
    assert {
        "learned/cells.jsonl checksum",
        "learned/flagship-cells.jsonl columns",
        "learned/final-evaluation.json router checksum",
        "learned/final-evaluation.json final matrix",
        "learned/flagship-study.json cp3_test matrix",
        "registry/ secrets",
    } <= names


def test_checksums_read_crlf_as_lf_like_the_report() -> None:
    path = DATA / "learned" / "cells.jsonl"
    assert validate.lf_sha256(path) == _sha256(path)


def test_a_changed_cell_fails_the_command(
    data_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    table = data_copy / "learned" / "cells.jsonl"
    rows = _rows(table)
    fresh = next(row for row in rows if row["suite"] == "final")
    fresh["correct"] = not fresh["correct"]
    _write_rows(table, rows)
    assert validate.main(["--data-dir", str(data_copy)]) == 1
    out = capsys.readouterr().out
    assert "FAIL  learned/cells.jsonl checksum: cells.meta.json says" in out
    assert not out.splitlines()[-1].endswith(" 0 failed")
    # With the meta brought up to date, the recomputed matrices still disagree with the reports.
    meta_path = table.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["cells_sha256"] = validate.lf_sha256(table)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert _failed(data_copy) == [
        "learned/final-evaluation.json final matrix",
        "learned/flagship-study.json final matrix",
    ]


def test_response_text_repeated_cells_and_unknown_prompts_fail(data_copy: Path) -> None:
    table = data_copy / "learned" / "flagship-cells.jsonl"
    rows = _rows(table)
    rows[0]["text"] = "The answer is 18."
    rows[2]["sample_id"] = "gsm8k-test-9999999"
    rows.append(dict(rows[1]))
    _write_rows(table, rows)
    failed = set(_failed(data_copy))
    assert {
        "learned/flagship-cells.jsonl checksum",
        "learned/flagship-cells.jsonl row counts",
        "learned/flagship-cells.jsonl unique cells",
        "learned/flagship-cells.jsonl prompts",
        "learned/flagship-cells.jsonl columns",
        "learned/flagship-study.json cell tables",
    } <= failed
    assert not any(name.startswith("learned/cells.jsonl") for name in failed)


def test_a_study_finds_its_cell_tables_by_prefix_or_by_its_list(data_copy: Path) -> None:
    learned = data_copy / "learned"
    (learned / "flagship-study.json").rename(learned / "frontier-study.json")
    for suffix in (".jsonl", ".meta.json"):
        (learned / f"flagship-cells{suffix}").rename(learned / f"frontier-cells{suffix}")
    study = learned / "frontier-study.json"
    report = json.loads(study.read_text(encoding="utf-8"))
    report.pop("cell_tables", None)  # without a list, the tables are found by the file prefix
    study.write_text(json.dumps(report), encoding="utf-8")
    assert _failed(data_copy) == []
    report["cell_tables"] = ["cells.jsonl", "frontier-cells.jsonl"]
    study.write_text(json.dumps(report), encoding="utf-8")
    assert _failed(data_copy) == []
    report["cell_tables"] = ["cells.jsonl"]  # the flagships' rows are then missing
    study.write_text(json.dumps(report), encoding="utf-8")
    assert _failed(data_copy) == [
        "learned/frontier-study.json cp3_test matrix",
        "learned/frontier-study.json final matrix",
    ]
    report["cell_tables"] = ["cells.jsonl", "elsewhere-cells.jsonl"]
    study.write_text(json.dumps(report), encoding="utf-8")
    assert _failed(data_copy) == ["learned/frontier-study.json cell tables"]


def test_a_key_in_a_data_file_fails_without_being_printed(
    data_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Built at run time, so no scanner mistakes this file for a leak.
    key = "sk-" + "or-v1-" + "0a1b2c3d" * 8
    token = "Ab3" * 12
    leak = data_copy / "registry" / "leak.json"
    leak.write_text(f'{{"note": "{key}"}}\n{{"header": "Bearer {token}"}}\n', encoding="utf-8")
    assert validate.main(["--data-dir", str(data_copy)]) == 1
    out = capsys.readouterr().out
    assert "FAIL  registry/ secrets: 3 secret-looking strings: registry/leak.json line 1 " \
        "(OpenRouter key prefix); registry/leak.json line 2 (bearer token); " \
        "registry/leak.json line 2 (long mixed-case token)" in out
    assert key not in out and token not in out
    assert "learned/ secrets" not in {name for name in _failed(data_copy)}


def test_unreadable_files_fail_instead_of_crashing(data_copy: Path) -> None:
    (data_copy / "learned" / "final-evaluation.json").write_text("{not json", encoding="utf-8")
    with (data_copy / "learned" / "cells.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    failed = _failed(data_copy)
    assert "learned/final-evaluation.json readable" in failed
    assert "learned/cells.jsonl readable" in failed
