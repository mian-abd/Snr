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


def estimate_worst_case_usd(models: list[ModelSpec], samples: list[BenchmarkSample]) -> Decimal:
    """Upper bound: ~4 characters per prompt token, full completion budget, every retry."""
    completion_tokens = Decimal(int(GENERATION_CONFIG["max_tokens"]))
    total = Decimal("0")
    for sample in samples:
        prompt_chars = len(SYSTEM_PROMPT) + len(render_prompt(sample.question))
        prompt_tokens = Decimal(prompt_chars // 4 + 16)
        for model in models:
            prompt_price = model.pricing.prompt_per_token or Decimal("0")
            completion_price = model.pricing.completion_per_token or Decimal("0")
            cell = prompt_tokens * prompt_price + completion_tokens * completion_price
            total += cell * MAX_ATTEMPTS_PER_CELL
    return total
