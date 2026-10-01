import pytest

from app.benchmarks.gsm8k import exact_match, extract_answer, load_samples, normalize_number
from app.config import REPOSITORY_ROOT


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$1,250", "1250"), ("-3", "-3"), ("2.500", "2.5"), ("+4", "4")],
)
def test_normalize_number(raw: str, expected: str) -> None:
    assert normalize_number(raw) == expected


@pytest.mark.parametrize(
    ("text", "answer", "method"),
    [
        ("Reasoning\nFINAL_ANSWER: $1,250", "1250", "final_answer"),
        (r"Therefore \\boxed{-3}.", "-3", "boxed"),
        ("We tried 2 and then obtained 7.5", "7.5", "last_number"),
        ("No numeric answer", None, None),
    ],
)
def test_extract_answer(text: str, answer: str | None, method: str | None) -> None:
    assert extract_answer(text) == (answer, method)


def test_exact_match_uses_decimal_equality() -> None:
    assert exact_match("2.0", "2") == 1
    assert exact_match(None, "2") == 0


def test_fixed_sample_has_expected_rows() -> None:
    samples = load_samples(REPOSITORY_ROOT / "data" / "benchmarks" / "gsm8k_checkpoint1.jsonl")
    assert len(samples) == 12
    assert [sample.expected_answer for sample in samples] == [
        "109", "8", "2", "4", "35", "22", "25", "110", "3", "225", "66", "30"
    ]
