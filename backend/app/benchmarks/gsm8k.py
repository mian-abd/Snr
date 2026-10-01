from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.domain.models import BenchmarkSample
from app.storage import read_jsonl

DATASET_NAME = "openai/gsm8k"
DATASET_CONFIGURATION = "main"
DATASET_SPLIT = "test"
SELECTION_SEED = 498
SOURCE_INDICES = (30, 263, 507, 509, 539, 756, 780, 851, 987, 1218, 1227, 1251)
PROMPT_TEMPLATE_VERSION = "gsm8k-cp1-v1"
SYSTEM_PROMPT = (
    "You are a careful grade-school math solver. Give concise reasoning and follow the "
    "required final-answer format."
)
PROMPT_TEMPLATE = """Solve the following problem. Show concise reasoning.
End with exactly one line in this form:
FINAL_ANSWER: <number>

{question}"""

NUMBER = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
FINAL_RE = re.compile(rf"FINAL_ANSWER\s*:\s*([$€£]?\s*{NUMBER})", re.IGNORECASE)
BOXED_RE = re.compile(rf"\\boxed\{{\s*([$€£]?\s*{NUMBER})\s*\}}", re.IGNORECASE)
NUMBER_RE = re.compile(rf"(?<![\w.])([$€£]?\s*{NUMBER})(?![\w.])")


def load_samples(path: Path) -> list[BenchmarkSample]:
    samples = [BenchmarkSample.model_validate(row) for row in read_jsonl(path)]
    if tuple(sample.source_index for sample in samples) != SOURCE_INDICES:
        raise ValueError("GSM8K sample indices do not match the Checkpoint 1 protocol")
    if len({sample.sample_id for sample in samples}) != len(samples):
        raise ValueError("GSM8K sample IDs must be unique")
    return samples


def render_prompt(question: str) -> str:
    return PROMPT_TEMPLATE.format(question=question)


def normalize_number(raw: str) -> str | None:
    cleaned = raw.strip().replace(",", "")
    cleaned = cleaned.lstrip("$€£").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value == value.to_integral():
        return str(value.quantize(Decimal("1")))
    return format(value.normalize(), "f")


def extract_answer(text: str | None) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    for method, pattern in (
        ("final_answer", FINAL_RE),
        ("boxed", BOXED_RE),
    ):
        match = pattern.search(text)
        if match:
            return normalize_number(match.group(1)), method
    matches = NUMBER_RE.findall(text)
    if matches:
        return normalize_number(matches[-1]), "last_number"
    return None, None


def exact_match(candidate: str | None, expected: str) -> int:
    candidate_value = normalize_number(candidate) if candidate is not None else None
    expected_value = normalize_number(expected)
    return int(candidate_value is not None and candidate_value == expected_value)
