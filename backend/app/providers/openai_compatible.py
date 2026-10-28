"""A project-owned adapter for OpenAI-compatible chat endpoints (OVHcloud, Ollama, AI Studio, NIM).

It makes exactly one HTTP request per attempt; retries stay in ``GenerationService`` so every
attempt is observable. Keys come from the given mapping or the environment at call time and are
never stored on results. Endpoints without a key (OVHcloud anonymous access, local Ollama) send
no auth header. ``request_options`` are merged into the request body, which is how an
OpenRouter upstream host is pinned (``provider.order`` with ``allow_fallbacks: false``).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

import httpx

from app.domain.models import CostSource, GenerationRequest, GenerationResult, GenerationStatus

PUBLIC_ERRORS = {
    GenerationStatus.RATE_LIMITED: "The provider's rate limit was reached. Wait and try again.",
    GenerationStatus.TIMEOUT: "The provider did not respond before the request timeout.",
    GenerationStatus.PROVIDER_ERROR: "The provider is temporarily unavailable or overloaded.",
    GenerationStatus.INVALID_RESPONSE: "The provider returned a response that could not be used.",
    GenerationStatus.MODEL_MISMATCH: "The provider served a different model than requested.",
}
# Google AI Studio returns Gemma 4's reasoning inline as a leading <thought> block and cannot
# turn it off; other providers return reasoning in a separate field. Scoring sees the answer only.
INLINE_THOUGHT_RE = re.compile(r"\A\s*<thought>.*?</thought>", re.DOTALL)


@dataclass(frozen=True)
class Endpoint:
    """How to reach one pinned model. ``model_id`` is the router-facing identity."""

    model_id: str
    provider: str
    base_url: str
    upstream_model: str
    prompt_price: Decimal = Decimal("0")
    completion_price: Decimal = Decimal("0")
    api_key_env: str | None = None
    request_options: dict[str, Any] = field(default_factory=dict)


def _same_model(served: str, upstream: str) -> bool:
    # Providers echo the model in different shapes ("models/x", "x:latest", casing).
    def normalize(value: str) -> str:
        return value.lower().rsplit("/", 1)[-1].removesuffix(":latest")

    return normalize(served) == normalize(upstream)


class OpenAICompatibleAdapter:
    def __init__(
        self,
        endpoints: list[Endpoint],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        keys: Mapping[str, str] | None = None,
    ) -> None:
        self.endpoints = {endpoint.model_id: endpoint for endpoint in endpoints}
        self.transport = transport
        self.keys = keys or {}

    def _result(
        self,
        request: GenerationRequest,
        endpoint: Endpoint,
        *,
        status: GenerationStatus,
        attempt_number: int,
        started_at: datetime,
        latency_ms: float,
        code: str | None = None,
        provider: str | None = None,
        **fields: Any,
    ) -> GenerationResult:
        return GenerationResult(
            request_id=request.request_id,
            requested_model_id=request.model_id,
            provider=provider or endpoint.provider,
            status=status,
            latency_ms=latency_ms,
            error_code=code,
            error_message=PUBLIC_ERRORS.get(status),
            started_at_utc=started_at,
            completed_at_utc=datetime.now(UTC),
            attempt_number=attempt_number,
            **fields,
        )

    async def generate(
        self, request: GenerationRequest, *, attempt_number: int = 1
    ) -> GenerationResult:
        endpoint = self.endpoints[request.model_id]
        headers = {"Content-Type": "application/json"}
        if endpoint.api_key_env:
            key = (
                self.keys.get(endpoint.api_key_env) or os.environ.get(endpoint.api_key_env, "")
            ).strip()
            if key:
                headers["Authorization"] = f"Bearer {key}"
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        body: dict[str, Any] = {
            **endpoint.request_options,
            "model": endpoint.upstream_model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        started_at = datetime.now(UTC)
        timer = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=request.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    f"{endpoint.base_url.rstrip('/')}/chat/completions", json=body, headers=headers
                )
        except httpx.TimeoutException:
            return self._result(
                request, endpoint, status=GenerationStatus.TIMEOUT, attempt_number=attempt_number,
                started_at=started_at, latency_ms=(perf_counter() - timer) * 1000, code="timeout",
            )
        except httpx.HTTPError as exc:
            return self._result(
                request, endpoint, status=GenerationStatus.PROVIDER_ERROR,
                attempt_number=attempt_number, started_at=started_at,
                latency_ms=(perf_counter() - timer) * 1000, code=type(exc).__name__,
            )
        latency_ms = (perf_counter() - timer) * 1000

        def finish(
            status: GenerationStatus, code: str | None = None, **fields: Any
        ) -> GenerationResult:
            return self._result(
                request, endpoint, status=status, attempt_number=attempt_number,
                started_at=started_at, latency_ms=latency_ms, code=code, **fields,
            )

        if response.status_code == 429:
            return finish(GenerationStatus.RATE_LIMITED, "429")
        if response.status_code >= 400:
            return finish(GenerationStatus.PROVIDER_ERROR, str(response.status_code))
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"].get("content")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            return finish(GenerationStatus.INVALID_RESPONSE, "malformed_response")
        served = str(data.get("model") or "") or None
        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        cost: Decimal | None = None
        cost_source = CostSource.UNAVAILABLE
        if usage.get("cost") is not None:
            # OpenRouter reports the billed cost of the host that actually served the call.
            cost, cost_source = Decimal(str(usage["cost"])), CostSource.PROVIDER
        elif prompt_tokens is not None and completion_tokens is not None:
            cost = (
                Decimal(int(prompt_tokens)) * endpoint.prompt_price
                + Decimal(int(completion_tokens)) * endpoint.completion_price
            )
            cost_source = CostSource.REGISTRY_CALCULATION
        host = data.get("provider")
        # Truncated and empty answers are still billed, so they keep their usage and cost.
        billed: dict[str, Any] = {
            "served_model_id": served,
            "prompt_tokens": int(prompt_tokens) if prompt_tokens is not None else None,
            "completion_tokens": int(completion_tokens) if completion_tokens is not None else None,
            "total_tokens": usage.get("total_tokens"),
            "cost_usd": cost,
            "cost_source": cost_source,
            "provider": f"{endpoint.provider}:{host}" if isinstance(host, str) and host else None,
        }
        if isinstance(content, str):
            content = INLINE_THOUGHT_RE.sub("", content, count=1)
            if content.lstrip().startswith("<thought>"):  # cut off before the answer began
                content = ""
        if not isinstance(content, str) or not content.strip():
            code = "truncated" if choice.get("finish_reason") == "length" else "empty_content"
            return finish(GenerationStatus.INVALID_RESPONSE, code, **billed)
        mismatch = served is not None and not _same_model(served, endpoint.upstream_model)
        return finish(
            GenerationStatus.MODEL_MISMATCH if mismatch else GenerationStatus.SUCCESS,
            "served_model_mismatch" if mismatch else None,
            text=content,
            **billed,
        )
