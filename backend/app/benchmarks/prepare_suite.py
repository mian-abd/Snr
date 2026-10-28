"""Build the fixed Checkpoint 3 benchmark suite from pinned sources.

Usage (from the repository root):

    uv run --project backend python -m app.benchmarks.prepare_suite

Downloads each source at a pinned revision or release, checks its SHA-256, draws a seeded sample,
assigns the router split, and writes ``data/benchmarks/cp3_suite.jsonl`` plus a ``.meta.json``
provenance record. Re-running with the same pins reproduces the same file byte for byte.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.benchmarks.gsm8k import SOURCE_INDICES as CHECKPOINT1_INDICES
from app.benchmarks.gsm8k import canonical_answer
from app.benchmarks.suite import (
    TASK_GROUPS,
    Benchmark,
    SuiteItem,
    assign_splits,
    split_counts,
)
from app.config import REPOSITORY_ROOT
from app.storage import atomic_write_json, atomic_write_jsonl

SEED = 2026
OUTPUT = REPOSITORY_ROOT / "data" / "benchmarks" / "cp3_suite.jsonl"
SAMPLE_SIZES = {
    Benchmark.GSM8K: 200,
    Benchmark.MMLU_PRO: 200,
    Benchmark.HUMANEVAL_PLUS: 100,
    Benchmark.MBPP_PLUS: 100,
}

# Every source is pinned to an exact revision or release and verified by SHA-256.
SOURCES: dict[Benchmark, dict[str, str]] = {
    Benchmark.GSM8K: {
        "kind": "hf",
        "dataset": "openai/gsm8k",
        "configuration": "main",
        "split": "test",
        "revision": "740312add88f781978c0658806c59bc2815b9866",
        "file": "main/test-00000-of-00001.parquet",
        "sha256": "ee7b8da9e381df27b9e3f7758a159ab2bdaa4dbaa910546cbbc47e0cb44e4f59",
        "license": "MIT",
    },
    Benchmark.MMLU_PRO: {
        "kind": "hf",
        "dataset": "TIGER-Lab/MMLU-Pro",
        "split": "test",
        "revision": "b189ec765aa7ed75c8acfea42df31fdae71f97be",
        "file": "data/test-00000-of-00001.parquet",
        "sha256": "0e24a191921c2f453518a537a8b2117bd137e7714d4ef1565e9ba06c1ecb9ad8",
        "license": "MIT",
    },
    Benchmark.HUMANEVAL_PLUS: {
        "kind": "release",
        "dataset": "evalplus/humanevalplus",
        "split": "test",
        "revision": "v0.1.10",
        "url": "https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz",
        "sha256": "272720b90ac375502c8ed23cd791c2a93dfb22a911641a494da74a426c09f101",
        "license": "Apache-2.0",
    },
    Benchmark.MBPP_PLUS: {
        "kind": "release",
        "dataset": "evalplus/mbppplus",
        "split": "test",
        "revision": "v0.2.0",
        "url": "https://github.com/evalplus/mbppplus_release/releases/download/v0.2.0/MbppPlus.jsonl.gz",
        "sha256": "af43697e8791c4c149bdfd6b489d8b5412507551ac20e28a439f650b8225db63",
        "license": "Apache-2.0",
    },
}


def _fetch(source: dict[str, str]) -> bytes:
    if source["kind"] == "hf":
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(
            source["dataset"], source["file"], repo_type="dataset", revision=source["revision"]
        )
        return Path(path).read_bytes()
    with urllib.request.urlopen(source["url"], timeout=120) as response:
        data: bytes = response.read()
        return data


def _verified_rows(benchmark: Benchmark) -> tuple[list[dict[str, Any]], str]:
    source = SOURCES[benchmark]
    data = _fetch(source)
    digest = hashlib.sha256(data).hexdigest()
    if source["sha256"] and digest != source["sha256"]:
        raise ValueError(f"{benchmark}: SHA-256 {digest} does not match pinned {source['sha256']}")
    if source["kind"] == "hf":
        import io

        import pyarrow.parquet as pq

        rows: list[dict[str, Any]] = pq.read_table(io.BytesIO(data)).to_pylist()
    else:
        rows = [json.loads(line) for line in gzip.decompress(data).decode().splitlines() if line]
    return rows, digest


def _gsm8k(rows: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    # Checkpoint 1's 12 questions shaped the rule router's thresholds, so they stay out.
    pool = [index for index in range(len(rows)) if index not in set(CHECKPOINT1_INDICES)]
    picked = sorted(rng.sample(pool, SAMPLE_SIZES[Benchmark.GSM8K]))
    return [
        {
            "sample_id": f"gsm8k-test-{index:04d}",
            "source_id": str(index),
            "question": rows[index]["question"],
            "expected_answer": canonical_answer(rows[index]["answer"]),
        }
        for index in picked
    ]


def _mmlu_pro(rows: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    # Stratify across the 14 categories so no single subject dominates.
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    categories = sorted(by_category)
    base, extra = divmod(SAMPLE_SIZES[Benchmark.MMLU_PRO], len(categories))
    quotas = {name: base + (1 if position < extra else 0) for position, name in enumerate(
        rng.sample(categories, len(categories))
    )}
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
    benchmark: Benchmark, rows: list[dict[str, Any]], rng: random.Random
) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: int(row["task_id"].split("/")[1]))
    picked = rng.sample(ordered, SAMPLE_SIZES[benchmark])
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


def build() -> tuple[list[SuiteItem], dict[str, Any]]:
    items: list[SuiteItem] = []
    provenance: dict[str, Any] = {}
    for offset, benchmark in enumerate(Benchmark):
        rows, digest = _verified_rows(benchmark)
        rng = random.Random(SEED + offset)
        if benchmark == Benchmark.GSM8K:
            drafts = _gsm8k(rows, rng)
        elif benchmark == Benchmark.MMLU_PRO:
            drafts = _mmlu_pro(rows, rng)
        else:
            drafts = _evalplus(benchmark, rows, rng)
        splits = assign_splits([draft["sample_id"] for draft in drafts], seed=SEED + 100 + offset)
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
                    router_split=splits[draft["sample_id"]],
                    **draft,
                )
            )
        provenance[benchmark.value] = {
            **{key: value for key, value in source.items() if key != "sha256"},
            "sha256": digest,
            "source_rows": len(rows),
            "sampled": len(drafts),
        }
    return items, provenance


def main() -> int:
    items, provenance = build()
    atomic_write_jsonl(OUTPUT, items)
    meta = {
        "suite": "cp3",
        "seed": SEED,
        "split_fractions": {"train": 0.6, "validation": 0.2, "test": 0.2},
        "excluded": {"gsm8k": list(CHECKPOINT1_INDICES)},
        "sources": provenance,
        "counts": split_counts(items),
        "suite_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    }
    atomic_write_json(OUTPUT.with_suffix(".meta.json"), meta)
    print(json.dumps(meta["counts"], indent=2))
    print(f"wrote {len(items)} items to {OUTPUT.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
