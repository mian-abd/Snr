from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Any

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm  # noqa: E402

from app.domain.models import (
    CostSource,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.registry.loader import ModelRegistry
from app.storage import sanitize_text


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class LiteLLMOpenRouterAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        registry: ModelRegistry,
        site_url: str,
        app_name: str,
    ) -> None:
        self.api_key = api_key
        self.registry = registry
        self.site_url = site_url
        self.app_name = app_name

    async def generate(
        self, request: GenerationRequest, *, attempt_number: int = 1
    ) -> GenerationResult:
        started_at = datetime.now(UTC)
        started_timer = perf_counter()
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        try:
            response = await litellm.acompletion(
                model=f"openrouter/{request.model_id}",
                messages=messages,
                api_key=self.api_key,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False,
                timeout=float(request.timeout_seconds),
                max_retries=0,
                drop_params=False,
                extra_headers={
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.app_name,
                },
            )
            completed_at = datetime.now(UTC)
            latency_ms = (perf_counter() - started_timer) * 1000
            choices = _get_value(response, "choices", []) or []
            if not choices:
                return self._error_result(
                    request=request,
                    attempt_number=attempt_number,
                    status=GenerationStatus.INVALID_RESPONSE,
                    code="empty_choices",
                    message="Provider returned no choices",
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=latency_ms,
                )
            message = _get_value(choices[0], "message", {})
            content = _get_value(message, "content")
            if not isinstance(content, str) or not content.strip():
                return self._error_result(
                    request=request,
                    attempt_number=attempt_number,
                    status=GenerationStatus.INVALID_RESPONSE,
                    code="empty_content",
                    message="Provider returned empty text content",
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=latency_ms,
                )
            served_model = str(_get_value(response, "model", "")) or None
            normalized_served = served_model.removeprefix("openrouter/") if served_model else None
            status = (
                GenerationStatus.SUCCESS
                if normalized_served == request.model_id
                else GenerationStatus.MODEL_MISMATCH
            )
            usage = _get_value(response, "usage", {}) or {}
            prompt_tokens = _get_value(usage, "prompt_tokens")
            completion_tokens = _get_value(usage, "completion_tokens")
            total_tokens = _get_value(usage, "total_tokens")
            provider_cost = _decimal_or_none(_get_value(usage, "cost"))
            hidden = _get_value(response, "_hidden_params", {}) or {}
            if provider_cost is None:
                provider_cost = _decimal_or_none(_get_value(hidden, "response_cost"))
            cost_source = (
                CostSource.PROVIDER if provider_cost is not None else CostSource.UNAVAILABLE
            )
            if (
                provider_cost is None
                and prompt_tokens is not None
                and completion_tokens is not None
            ):
                pricing = self.registry.get(request.model_id).pricing
                if (
                    pricing.prompt_per_token is not None
                    and pricing.completion_per_token is not None
                ):
                    provider_cost = (
                        Decimal(int(prompt_tokens)) * pricing.prompt_per_token
                        + Decimal(int(completion_tokens)) * pricing.completion_per_token
                    )
                    cost_source = CostSource.REGISTRY_CALCULATION
            return GenerationResult(
                request_id=request.request_id,
                requested_model_id=request.model_id,
                served_model_id=normalized_served,
                status=status,
                text=content,
                prompt_tokens=int(prompt_tokens) if prompt_tokens is not None else None,
                completion_tokens=(
                    int(completion_tokens) if completion_tokens is not None else None
                ),
                total_tokens=int(total_tokens) if total_tokens is not None else None,
                latency_ms=latency_ms,
                cost_usd=provider_cost,
                cost_source=cost_source,
                provider_request_id=str(_get_value(response, "id", "")) or None,
                error_code=(
                    "served_model_mismatch"
                    if status == GenerationStatus.MODEL_MISMATCH
                    else None
                ),
                error_message=(
                    f"Expected {request.model_id}, received {normalized_served}"
                    if status == GenerationStatus.MODEL_MISMATCH
                    else None
                ),
                started_at_utc=started_at,
                completed_at_utc=completed_at,
                attempt_number=attempt_number,
            )
        except Exception as exc:  # LiteLLM normalizes many provider exception classes.
            completed_at = datetime.now(UTC)
            latency_ms = (perf_counter() - started_timer) * 1000
            status_code = getattr(exc, "status_code", None)
            name = type(exc).__name__.lower()
            if status_code == 429 or "ratelimit" in name:
                status = GenerationStatus.RATE_LIMITED
            elif status_code == 408 or "timeout" in name:
                status = GenerationStatus.TIMEOUT
            else:
                status = GenerationStatus.PROVIDER_ERROR
            safe_message = sanitize_text(str(exc), secrets=(self.api_key,))
            return self._error_result(
                request=request,
                attempt_number=attempt_number,
                status=status,
                code=str(status_code or type(exc).__name__),
                message=safe_message[:1000],
                started_at=started_at,
                completed_at=completed_at,
                latency_ms=latency_ms,
            )

    @staticmethod
    def _error_result(
        *,
        request: GenerationRequest,
        attempt_number: int,
        status: GenerationStatus,
        code: str,
        message: str,
        started_at: datetime,
        completed_at: datetime,
        latency_ms: float,
    ) -> GenerationResult:
        return GenerationResult(
            request_id=request.request_id,
            requested_model_id=request.model_id,
            status=status,
            latency_ms=latency_ms,
            error_code=code,
            error_message=message,
            started_at_utc=started_at,
            completed_at_utc=completed_at,
            attempt_number=attempt_number,
        )
