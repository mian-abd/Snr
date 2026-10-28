import json

from app.benchmarks.code_scoring import SANDBOX_FLAGS, STUB, parse_results, write_samples
from app.benchmarks.suite import Benchmark
from app.storage import read_jsonl


def test_samples_cover_every_task_and_stub_the_unsampled_ones(tmp_path) -> None:
    path = tmp_path / "humaneval.jsonl"
    write_samples(
        Benchmark.HUMANEVAL_PLUS,
        {"HumanEval/1": "def f():\n    return 1\n"},
        ["HumanEval/0", "HumanEval/1", "HumanEval/2"],
        path,
    )
    rows = read_jsonl(path)
    assert [row["task_id"] for row in rows] == ["HumanEval/0", "HumanEval/1", "HumanEval/2"]
    assert rows[1]["solution"].startswith("def f()")
    assert rows[0]["solution"] == STUB and rows[2]["solution"] == STUB


def test_a_task_passes_only_when_base_and_extra_tests_pass(tmp_path) -> None:
    results = tmp_path / "humaneval-sanitized_eval_results.json"
    results.write_text(json.dumps({"eval": {
        "HumanEval/0": [{"base_status": "pass", "plus_status": "pass"}],
        "HumanEval/1": [{"base_status": "pass", "plus_status": "fail"}],
        "HumanEval/2": [{"base_status": "fail", "plus_status": None}],
    }}), encoding="utf-8")
    parsed = parse_results(results)
    assert [parsed[task]["passed"] for task in sorted(parsed)] == [True, False, False]


def test_sandbox_has_no_network_and_drops_privileges() -> None:
    flags = " ".join(SANDBOX_FLAGS)
    assert "--network none" in flags
    assert "--cap-drop ALL" in flags
    assert "no-new-privileges" in flags
    assert "--memory 8g" in flags and "--pids-limit 512" in flags
