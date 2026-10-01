from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from app.domain.models import (
    GenerationOutcome,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.providers.base import ModelAdapter

AttemptCallback = Callable[[GenerationResult], Awaitable[None]]


class GenerationService:
    def __init__(self, adapter: ModelAdapter) -> None:
        self.adapter = adapter

    async def generate_with_retries(
        self,
        request: GenerationRequest,
        *,
        start_attempt: int = 1,
        max_attempts: int = 2,
        on_attempt: AttemptCallback | None = None,
    ) -> GenerationOutcome:
        attempts: list[GenerationResult] = []
        for attempt_number in range(start_attempt, max_attempts + 1):
            result = await self.adapter.generate(request, attempt_number=attempt_number)
            attempts.append(result)
            if on_attempt:
                await on_attempt(result)
            if not self.is_retryable(result) or attempt_number >= max_attempts:
                break
            await asyncio.sleep(2 + random.uniform(0, 0.35))
        return GenerationOutcome(final=attempts[-1], attempts=attempts)

    @staticmethod
    def is_retryable(result: GenerationResult) -> bool:
        if result.status in {GenerationStatus.TIMEOUT, GenerationStatus.RATE_LIMITED}:
            return True
        if result.status != GenerationStatus.PROVIDER_ERROR:
            return False
        try:
            status_code = int(result.error_code or "0")
        except ValueError:
            return True
        return status_code >= 500 or status_code in {408, 429}
