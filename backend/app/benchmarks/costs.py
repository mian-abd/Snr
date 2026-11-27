"""Paid-run settings and the worst-case cost estimate shared by the CLI and the API."""

from __future__ import annotations

from decimal import Decimal

from app.benchmarks.gsm8k import SYSTEM_PROMPT, render_prompt
from app.benchmarks.runner import GENERATION_CONFIG
from app.domain.models import BenchmarkSample, ModelSpec

PAID_DEMO_NAME = "checkpoint-2-paid"
PAID_RUN_PREFIX = "gsm8k-paid"
PAID_BUDGET_FILE = "paid-provider-request-budget.json"
PAID_MAX_REQUESTS = 100
SPEND_CAP_USD = Decimal("1.00")
MAX_ATTEMPTS_PER_CELL = 2


def worst_case_call_usd(
    prompt_tokens: int,
    max_tokens: int,
    prompt_price_per_token: Decimal | None,
    completion_price_per_token: Decimal | None,
    attempts: int = MAX_ATTEMPTS_PER_CELL,
) -> Decimal:
    """Upper bound for one call: every prompt token, the full completion budget, every retry."""
    one_attempt = Decimal(prompt_tokens) * (prompt_price_per_token or Decimal("0")) + Decimal(
        max_tokens
    ) * (completion_price_per_token or Decimal("0"))
    return one_attempt * attempts


def estimate_worst_case_usd(models: list[ModelSpec], samples: list[BenchmarkSample]) -> Decimal:
    """Upper bound: ~4 characters per prompt token, full completion budget, every retry."""
    completion_tokens = int(GENERATION_CONFIG["max_tokens"])
    total = Decimal("0")
    for sample in samples:
        prompt_chars = len(SYSTEM_PROMPT) + len(render_prompt(sample.question))
        prompt_tokens = prompt_chars // 4 + 16
        for model in models:
            total += worst_case_call_usd(
                prompt_tokens,
                completion_tokens,
                model.pricing.prompt_per_token,
                model.pricing.completion_per_token,
            )
    return total
