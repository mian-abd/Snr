from types import SimpleNamespace

import pytest

from app.domain.models import GenerationRequest, GenerationStatus
from app.providers.litellm_openrouter import LiteLLMOpenRouterAdapter


@pytest.mark.asyncio
async def test_adapter_normalizes_success(monkeypatch, registry) -> None:
    async def fake_completion(**kwargs):
        assert kwargs["max_retries"] == 0
        assert kwargs["model"].startswith("openrouter/")
        return SimpleNamespace(
            id="provider-request",
            model="google/gemma-4-26b-a4b-it:free",
            choices=[SimpleNamespace(message=SimpleNamespace(content="FINAL_ANSWER: 4"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14, cost=0),
            _hidden_params={},
        )

    monkeypatch.setattr("app.providers.litellm_openrouter.litellm.acompletion", fake_completion)
    adapter = LiteLLMOpenRouterAdapter(
        api_key="test-key", registry=registry, site_url="http://test", app_name="test"
    )
    result = await adapter.generate(
        GenerationRequest(model_id=registry.models[0].id, prompt="2+2")
    )
    assert result.status == GenerationStatus.SUCCESS
    assert result.total_tokens == 14
    assert result.provider_request_id == "provider-request"


@pytest.mark.asyncio
async def test_adapter_handles_rate_limit_without_leaking_key(monkeypatch, registry) -> None:
    class RateLimitError(Exception):
        status_code = 429

    async def fake_completion(**kwargs):
        raise RateLimitError("bad test-key")

    monkeypatch.setattr("app.providers.litellm_openrouter.litellm.acompletion", fake_completion)
    adapter = LiteLLMOpenRouterAdapter(
        api_key="test-key", registry=registry, site_url="http://test", app_name="test"
    )
    result = await adapter.generate(
        GenerationRequest(model_id=registry.models[0].id, prompt="hello")
    )
    assert result.status == GenerationStatus.RATE_LIMITED
    assert "test-key" not in (result.error_message or "")
