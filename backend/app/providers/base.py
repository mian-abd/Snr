from typing import Protocol

from app.domain.models import GenerationRequest, GenerationResult


class ModelAdapter(Protocol):
    async def generate(
        self, request: GenerationRequest, *, attempt_number: int = 1
    ) -> GenerationResult: ...
