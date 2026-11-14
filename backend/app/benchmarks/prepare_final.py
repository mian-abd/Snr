"""Build the final held-out set: fresh prompts drawn after the learned router was frozen.

Usage (from the repository root):

    uv run --project backend python -m app.benchmarks.prepare_final

The Checkpoint 3 test split (120 prompts) was read once to report the router. The final
evaluation (proposal, week of Nov 19) uses prompts that no model, router, or analysis has seen:
the same four pinned, checksum-verified sources, minus every prompt in the 600-prompt suite and
Checkpoint 1's 12 GSM8K questions. The draw uses its own seed, the file and its SHA-256 are
written before any model answers it (each run's manifest records that hash), and re-running
reproduces it byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from typing import Any

from app.benchmarks.gsm8k import SOURCE_INDICES as CHECKPOINT1_INDICES
from app.benchmarks.gsm8k import canonical_answer
from app.benchmarks.prepare_suite import OUTPUT as SUITE_PATH
from app.benchmarks.prepare_suite import SOURCES, _verified_rows
from app.benchmarks.suite import (
    TASK_GROUPS,
    Benchmark,
    RouterSplit,
    SuiteItem,
    load_suite,
    split_counts,
)
from app.config import REPOSITORY_ROOT
from app.storage import atomic_write_json, atomic_write_jsonl

FINAL_SEED = 20261119
OUTPUT = REPOSITORY_ROOT / "data" / "benchmarks" / "final_heldout.jsonl"
FINAL_SIZES = {
    Benchmark.GSM8K: 100,
    Benchmark.MMLU_PRO: 100,
    Benchmark.HUMANEVAL_PLUS: 50,
    Benchmark.MBPP_PLUS: 50,
}


def _gsm8k(rows: list[dict[str, Any]], used: set[str], rng: random.Random) -> list[dict[str, Any]]:
    blocked = used | {str(index) for index in CHECKPOINT1_INDICES}
    pool = [index for index in range(len(rows)) if str(index) not in blocked]
    picked = sorted(rng.sample(pool, FINAL_SIZES[Benchmark.GSM8K]))
    return [
        {
            "sample_id": f"gsm8k-test-{index:04d}",
            "source_id": str(index),
            "question": rows[index]["question"],
            "expected_answer": canonical_answer(rows[index]["answer"]),
        }
        for index in picked
    ]


def _mmlu_pro(
    rows: list[dict[str, Any]], used: set[str], rng: random.Random
) -> list[dict[str, Any]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row["question_id"]) not in used:
            by_category[row["category"]].append(row)
    categories = sorted(by_category)
    base, extra = divmod(FINAL_SIZES[Benchmark.MMLU_PRO], len(categories))
    quotas = {
        name: base + (1 if position < extra else 0)
        for position, name in enumerate(rng.sample(categories, len(categories)))
    }
    picked: list[dict[str, Any]] = []
    for name in categories:
        candidates = sorted(by_category[name], key=lambda row: int(row["question_id"]))
        picked.extend(rng.sample(candidates, quotas[name]))
    return [
        {
            "sample_id": f"mmlu_pro-test-{int(row['question_id']):05d}",
            "source_id": str(row["question_id"]),
            "category": row["category"],
            "question": row["question"],
            "options": [str(option) for option in row["options"]],
            "expected_answer": row["answer"],
        }
        for row in sorted(picked, key=lambda row: int(row["question_id"]))
    ]


def _evalplus(
    benchmark: Benchmark, rows: list[dict[str, Any]], used: set[str], rng: random.Random
) -> list[dict[str, Any]]:
    ordered = sorted(
        (row for row in rows if row["task_id"] not in used),
        key=lambda row: int(row["task_id"].split("/")[1]),
    )
    picked = rng.sample(ordered, FINAL_SIZES[benchmark])
    prefix = "humaneval_plus" if benchmark == Benchmark.HUMANEVAL_PLUS else "mbpp_plus"
    return [
        {
            "sample_id": f"{prefix}-{row['task_id'].split('/')[1].zfill(3)}",
            "source_id": row["task_id"],
            "question": row["prompt"],
            "entry_point": row["entry_point"],
        }
        for row in sorted(picked, key=lambda row: int(row["task_id"].split("/")[1]))
    ]


def build(suite: list[SuiteItem]) -> tuple[list[SuiteItem], dict[str, Any]]:
    used: dict[Benchmark, set[str]] = defaultdict(set)
    for item in suite:
        used[item.benchmark].add(item.source_id)
    items: list[SuiteItem] = []
    provenance: dict[str, Any] = {}
    for offset, benchmark in enumerate(Benchmark):
        rows, digest = _verified_rows(benchmark)
        rng = random.Random(FINAL_SEED + offset)
        if benchmark == Benchmark.GSM8K:
            drafts = _gsm8k(rows, used[benchmark], rng)
        elif benchmark == Benchmark.MMLU_PRO:
            drafts = _mmlu_pro(rows, used[benchmark], rng)
        else:
            drafts = _evalplus(benchmark, rows, used[benchmark], rng)
        source = SOURCES[benchmark]
        for draft in drafts:
            items.append(
                SuiteItem(
                    benchmark=benchmark,
                    task_group=TASK_GROUPS[benchmark],
                    dataset=source["dataset"],
                    configuration=source.get("configuration"),
                    source_split=source["split"],
                    revision=source["revision"],
                    router_split=RouterSplit.FINAL,
                    **draft,
                )
            )
        provenance[benchmark.value] = {
            **{key: value for key, value in source.items() if key != "sha256"},
            "sha256": digest,
            "source_rows": len(rows),
            "excluded_as_used": len(used[benchmark])
            + (len(CHECKPOINT1_INDICES) if benchmark == Benchmark.GSM8K else 0),
            "sampled": len(drafts),
        }
    overlap = {item.sample_id for item in items} & {item.sample_id for item in suite}
    if overlap:
        raise RuntimeError(f"Final prompts overlap the suite: {sorted(overlap)[:5]}")
    return items, provenance


def main() -> int:
    suite = load_suite(SUITE_PATH)
    items, provenance = build(suite)
    atomic_write_jsonl(OUTPUT, items)
    meta = {
        "suite": "final-heldout",
        "seed": FINAL_SEED,
        "drawn_after": "the learned router was exported and evaluated on the Checkpoint 3 test "
        "split (data/learned/cp3-router-model.json)",
        "excluded": {
            "cp3_suite_sha256": hashlib.sha256(SUITE_PATH.read_bytes()).hexdigest(),
            "gsm8k_checkpoint1_indices": list(CHECKPOINT1_INDICES),
        },
        "sources": provenance,
        "counts": split_counts(items),
        "final_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    }
    atomic_write_json(OUTPUT.with_suffix(".meta.json"), meta)
    print(json.dumps(meta["counts"], indent=2))
    print(f"wrote {len(items)} items to {OUTPUT.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
