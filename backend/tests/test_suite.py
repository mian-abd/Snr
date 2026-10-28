from app.benchmarks.suite import (
    Benchmark,
    RouterSplit,
    SuiteItem,
    TaskGroup,
    assign_splits,
    load_suite,
    split_counts,
)
from app.benchmarks.tasks import extract, extract_code, max_tokens, render_prompt
from app.config import REPOSITORY_ROOT

SUITE = REPOSITORY_ROOT / "data" / "benchmarks" / "cp3_suite.jsonl"


def _item(benchmark: Benchmark, **overrides) -> SuiteItem:
    groups = {
        Benchmark.GSM8K: TaskGroup.MATH,
        Benchmark.MMLU_PRO: TaskGroup.QA,
        Benchmark.HUMANEVAL_PLUS: TaskGroup.CODE,
        Benchmark.MBPP_PLUS: TaskGroup.CODE,
    }
    fields = {
        "sample_id": f"{benchmark.value}-x",
        "benchmark": benchmark,
        "task_group": groups[benchmark],
        "dataset": "d",
        "source_split": "test",
        "revision": "r",
        "source_id": "1",
        "question": "q",
        "router_split": RouterSplit.TRAIN,
    }
    fields.update(overrides)
    return SuiteItem(**fields)


def test_committed_suite_has_600_items_and_a_60_20_20_split_per_benchmark() -> None:
    items = load_suite(SUITE)
    assert len(items) == 600
    assert split_counts(items) == {
        "gsm8k": {"train": 120, "validation": 40, "test": 40},
        "humaneval_plus": {"train": 60, "validation": 20, "test": 20},
        "mbpp_plus": {"train": 60, "validation": 20, "test": 20},
        "mmlu_pro": {"train": 120, "validation": 40, "test": 40},
    }
    checkpoint1 = {30, 263, 507, 509, 539, 756, 780, 851, 987, 1218, 1227, 1251}
    gsm8k_indices = {int(item.source_id) for item in items if item.benchmark == Benchmark.GSM8K}
    assert not checkpoint1 & gsm8k_indices
    assert all(item.entry_point for item in items if item.task_group == TaskGroup.CODE)
    assert all(item.expected_answer for item in items if item.task_group != TaskGroup.CODE)


def test_split_assignment_is_deterministic_and_order_independent() -> None:
    ids = [f"s{i}" for i in range(10)]
    first = assign_splits(ids, seed=7)
    assert first == assign_splits(list(reversed(ids)), seed=7)
    assert list(first.values()).count(RouterSplit.TRAIN) == 6
    assert list(first.values()).count(RouterSplit.TEST) == 2


def test_mmlu_pro_prompt_and_official_extraction_order() -> None:
    item = _item(
        Benchmark.MMLU_PRO, category="physics", options=["one", "two", "three", "four"],
        expected_answer="C",
    )
    _, prompt = render_prompt(item)
    assert "A. one\nB. two\nC. three\nD. four" in prompt
    assert prompt.endswith("Let's think step by step.")
    assert extract(item, "Reasoning... The answer is (C).").correct is True
    assert extract(item, "So the final Answer: B").answer == "B"
    # Letters beyond the offered options are ignored, and no match is wrong, not a guess.
    assert extract(item, "The answer is (J)").answer is None
    assert extract(item, "I am not sure.").correct is False
    assert max_tokens(item) == 4096


def test_gsm8k_reuses_the_checkpoint_scorer() -> None:
    item = _item(Benchmark.GSM8K, expected_answer="42")
    system, prompt = render_prompt(item)
    assert system and "FINAL_ANSWER" in prompt
    assert extract(item, "work...\nFINAL_ANSWER: 42").correct is True
    assert extract(item, None).correct is False


def test_code_extraction_prefers_the_longest_block_and_defers_scoring() -> None:
    item = _item(Benchmark.HUMANEVAL_PLUS, entry_point="add")
    text = (
        "Here:\n```python\ndef add(a, b):\n    return a + b\n```\n"
        "Usage:\n```python\nadd(1, 2)\n```"
    )
    result = extract(item, text)
    assert result.answer == "def add(a, b):\n    return a + b\n"
    assert result.correct is None
    assert extract_code("def f():\n    pass")[1] == "raw_text"
    assert "markdown code block" in render_prompt(item)[1]
