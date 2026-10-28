"""Score generated code with EvalPlus inside a locked-down Docker container.

    uv run --project backend python -m app.benchmarks.code_scoring --run-id cp3-full

Generated code never runs on the host. Each model's answers are written as an EvalPlus samples
file and scored by the pinned ``ganler/evalplus`` image with no network, capped memory, CPU and
process counts, no added privileges, and all Linux capabilities dropped. A task passes only when
both the base tests and the extra EvalPlus tests pass ("Base + Extra", greedy pass@1).
EvalPlus requires a solution for every task in a dataset, so tasks outside our sample get a stub
whose result is ignored. Because the container has no network, EvalPlus reads the same pinned,
checksum-verified dataset files the suite was built from, through its override variables.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from app.benchmarks.prepare_suite import _verified_rows
from app.benchmarks.suite import Benchmark, SuiteItem, TaskGroup, load_suite
from app.config import REPOSITORY_ROOT
from app.storage import atomic_write_jsonl, read_jsonl

# Pinned by digest as well as tag; the package inside reports version 0.4.0.dev2.
IMAGE = (
    "ganler/evalplus:v0.3.1"
    "@sha256:26b118098bef281fe8dfe999bf05f1d5b45374b4e6c00161ec0f30592aef4740"
)
SUITE_PATH = REPOSITORY_ROOT / "data" / "benchmarks" / "cp3_suite.jsonl"
RUNS_DIR = REPOSITORY_ROOT / "data" / "local" / "cp3"
DATA_DIR = RUNS_DIR / "evalplus-data"  # mounted read-only, so answers cannot alter the tests
DATASETS = {Benchmark.HUMANEVAL_PLUS: "humaneval", Benchmark.MBPP_PLUS: "mbpp"}
DATASET_OVERRIDES = {
    Benchmark.HUMANEVAL_PLUS: ("HUMANEVAL_OVERRIDE_PATH", "HumanEvalPlus.jsonl"),
    Benchmark.MBPP_PLUS: ("MBPP_OVERRIDE_PATH", "MbppPlus.jsonl"),
}
STUB = "# not part of the sampled suite\n"
SANDBOX_FLAGS = [
    "--rm",
    "--network", "none",
    "--memory", "8g",
    "--memory-swap", "8g",
    "--cpus", "4",
    "--pids-limit", "512",
    "--security-opt", "no-new-privileges",
    "--cap-drop", "ALL",
]


def docker(workdir: Path, benchmark: Benchmark, *command: str) -> None:
    variable, filename = DATASET_OVERRIDES[benchmark]
    subprocess.run(
        ["docker", "run", *SANDBOX_FLAGS, "-e", f"{variable}=/data/{filename}",
         "-v", f"{workdir.resolve()}:/app", "-v", f"{DATA_DIR.resolve()}:/data:ro",
         IMAGE, *command],
        check=True,
    )


def write_samples(
    benchmark: Benchmark,
    answers: dict[str, str],
    all_task_ids: list[str],
    path: Path,
) -> None:
    rows = [
        {"task_id": task_id, "solution": answers.get(task_id, STUB)} for task_id in all_task_ids
    ]
    atomic_write_jsonl(path, rows)


def parse_results(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    parsed: dict[str, dict[str, Any]] = {}
    for task_id, runs in data["eval"].items():
        run = runs[0]
        parsed[task_id] = {
            "base_status": run.get("base_status"),
            "plus_status": run.get("plus_status"),
            "passed": run.get("base_status") == "pass" and run.get("plus_status") == "pass",
        }
    return parsed


def score_model(
    model_dir: Path, items: dict[str, SuiteItem], task_ids: dict[Benchmark, list[str]]
) -> int:
    pending: dict[Benchmark, dict[str, tuple[str, str]]] = {benchmark: {} for benchmark in DATASETS}
    for row in read_jsonl(model_dir / "results.jsonl"):
        item = items.get(row["sample_id"])
        if item is None or item.task_group != TaskGroup.CODE:
            continue
        if row["correct"] is None and row["extracted_answer"]:
            pending[item.benchmark][item.source_id] = (item.sample_id, row["extracted_answer"])
    scored: list[dict[str, Any]] = []
    workdir = model_dir / "evalplus"
    for benchmark, answers in pending.items():
        if not answers:
            continue
        dataset = DATASETS[benchmark]
        samples = workdir / f"{dataset}.jsonl"
        write_samples(
            benchmark,
            {task_id: code for task_id, (_, code) in answers.items()},
            task_ids[benchmark],
            samples,
        )
        docker(workdir, benchmark, "evalplus.sanitize", "--samples", f"/app/{dataset}.jsonl")
        docker(
            workdir, benchmark, "evalplus.evaluate", "--dataset", dataset,
            "--samples", f"/app/{dataset}-sanitized.jsonl", "--parallel", "4",
        )
        results = parse_results(workdir / f"{dataset}-sanitized_eval_results.json")
        for task_id, (sample_id, _) in answers.items():
            scored.append({"model_id": model_dir.name, "sample_id": sample_id, "task_id": task_id,
                           "evalplus_image": IMAGE, **results[task_id]})
    if scored:
        atomic_write_jsonl(model_dir / "code_scores.jsonl", scored)
    return len(scored)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", default="cp3-full")
    parser.add_argument("--models", help="Comma-separated model IDs (default: all in the run)")
    args = parser.parse_args()
    items = {item.sample_id: item for item in load_suite(SUITE_PATH)}
    task_ids: dict[Benchmark, list[str]] = {}
    for benchmark in DATASETS:
        rows = _verified_rows(benchmark)[0]
        atomic_write_jsonl(DATA_DIR / DATASET_OVERRIDES[benchmark][1], rows)
        task_ids[benchmark] = [row["task_id"] for row in rows]
    subprocess.run(["docker", "pull", IMAGE], check=True)
    wanted = set(args.models.split(",")) if args.models else None
    for model_dir in sorted(path for path in (RUNS_DIR / args.run_id).iterdir() if path.is_dir()):
        if wanted and model_dir.name not in wanted:
            continue
        count = score_model(model_dir, items, task_ids)
        print(f"{model_dir.name}: scored {count} code answers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
