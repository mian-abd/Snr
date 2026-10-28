"""Per-benchmark prompts, generation budgets, and answer extraction for the Checkpoint 3 suite.

Math and multiple-choice answers are scored here, deterministically and without an LLM judge.
Code answers are only extracted here; they are scored later by EvalPlus inside a network-less
Docker sandbox, because generated code must never run directly on the host.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass

from app.benchmarks import gsm8k
from app.benchmarks.suite import Benchmark, SuiteItem, TaskGroup

SUITE_PROMPT_VERSION = "cp3-v2"

# Generous enough that only runaway generations hit them; truncation counts as a failure.
# cp3-v1 used 1,024 / 2,048 / 2,048 and truncated reasoning-by-default models on ordinary
# questions, which measured default reasoning length rather than ability, so it was abandoned.
MAX_TOKENS = {TaskGroup.MATH: 2048, TaskGroup.QA: 4096, TaskGroup.CODE: 4096}

MMLU_PRO_TEMPLATE = (
    "The following is a multiple choice question about {category}. Think step by step and "
    'then finish your answer with "The answer is (X)" where X is the correct letter choice.\n\n'
    "Question:\n{question}\nOptions:\n{options}\nAnswer: Let's think step by step."
)
# EvalPlus's instruction prefix for chat models (evalplus/codegen.py).
CODE_TEMPLATE = (
    "Please provide a self-contained Python script that solves the following problem in a "
    "markdown code block:\n```\n{prompt}\n```"
)
CODE_BLOCK_RE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class Extraction:
    answer: str | None
    method: str | None
    correct: bool | None  # None means "scored later" (code)


def letters_for(item: SuiteItem) -> str:
    return string.ascii_uppercase[: len(item.options)]


def render_prompt(item: SuiteItem) -> tuple[str | None, str]:
    """Return (system prompt, user prompt)."""
    if item.benchmark == Benchmark.GSM8K:
        return gsm8k.SYSTEM_PROMPT, gsm8k.render_prompt(item.question)
    if item.benchmark == Benchmark.MMLU_PRO:
        options = "\n".join(
            f"{letter}. {option}"
            for letter, option in zip(letters_for(item), item.options, strict=True)
        )
        return None, MMLU_PRO_TEMPLATE.format(
            category=item.category or "general knowledge", question=item.question, options=options
        )
    return None, CODE_TEMPLATE.format(prompt=item.question.strip())


def max_tokens(item: SuiteItem) -> int:
    return MAX_TOKENS[item.task_group]


def _mmlu_letter(text: str, valid: str) -> tuple[str | None, str | None]:
    # The official MMLU-Pro extraction order, restricted to letters this question offers.
    allowed = f"[{valid}]"
    for method, pattern, flags in (
        ("answer_is", rf"answer is \(?({allowed})\)?", 0),
        ("answer_colon", rf".*[aA]nswer:\s*({allowed})", 0),
        ("last_letter", rf"\b({allowed})\b(?!.*\b{allowed}\b)", re.DOTALL),
    ):
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1), method
    return None, None


def extract_code(text: str) -> tuple[str | None, str | None]:
    blocks = CODE_BLOCK_RE.findall(text)
    if blocks:
        # Prefer the longest block; models sometimes add a short usage example afterwards.
        return max(blocks, key=len).strip("\n") + "\n", "code_block"
    stripped = text.strip()
    return (stripped + "\n", "raw_text") if stripped else (None, None)


def extract(item: SuiteItem, text: str | None) -> Extraction:
    if not text:
        return Extraction(None, None, None if item.task_group == TaskGroup.CODE else False)
    if item.benchmark == Benchmark.GSM8K:
        answer, method = gsm8k.extract_answer(text)
        assert item.expected_answer is not None
        return Extraction(answer, method, bool(gsm8k.exact_match(answer, item.expected_answer)))
    if item.benchmark == Benchmark.MMLU_PRO:
        letter, method = _mmlu_letter(text, letters_for(item))
        # Unlike the official script, a failed extraction is wrong, not a random guess.
        return Extraction(letter, method, letter is not None and letter == item.expected_answer)
    code, method = extract_code(text)
    return Extraction(code, method, None)
