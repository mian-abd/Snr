from decimal import Decimal

import httpx
import pytest

from app.domain.models import CostSource, GenerationRequest, GenerationStatus
from app.providers.openai_compatible import Endpoint, OpenAICompatibleAdapter

FREE = Endpoint("ovh/qwen", "ovhcloud", "https://example.test/v1", "Qwen3.8-27B")
PAID = Endpoint(
    "nim/deepseek",
    "nvidia_nim",
    "https://nim.test/v1/",
    "deepseek-ai/deepseek-v4.1-flash",
    prompt_price=Decimal("0.000001"),
    completion_price=Decimal("0.000002"),
    api_key_env="TEST_NIM_KEY",
)


def _adapter(handler) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter([FREE, PAID], transport=httpx.MockTransport(handler))


def _completion(model: str, content: str | None, finish: str = "stop") -> dict:
    return {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


@pytest.mark.asyncio
async def test_success_computes_cost_and_sends_key_only_when_configured(monkeypatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        model = "deepseek-ai/deepseek-v4.1-flash" if "nim" in str(request.url) else "Qwen3.8-27B"
        return httpx.Response(200, json=_completion(model, "FINAL_ANSWER: 4"))

    monkeypatch.setenv("TEST_NIM_KEY", "secret-value")
    adapter = _adapter(handler)
    paid = await adapter.generate(GenerationRequest(model_id="nim/deepseek", prompt="2+2?"))
    free = await adapter.generate(GenerationRequest(model_id="ovh/qwen", prompt="2+2?"))

    assert paid.status == GenerationStatus.SUCCESS
    assert paid.cost_usd == Decimal("0.0002")
    assert paid.cost_source == CostSource.REGISTRY_CALCULATION
    assert str(seen[0].url) == "https://nim.test/v1/chat/completions"
    assert seen[0].headers["Authorization"] == "Bearer secret-value"
    assert "Authorization" not in seen[1].headers
    assert free.cost_usd == Decimal("0")
    assert free.provider == "ovhcloud"
    assert "secret-value" not in paid.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "status", "code"),
    [
        (httpx.Response(429, json={}), GenerationStatus.RATE_LIMITED, "429"),
        (httpx.Response(503, json={}), GenerationStatus.PROVIDER_ERROR, "503"),
        (httpx.Response(200, text="not json"), GenerationStatus.INVALID_RESPONSE, "malformed_response"),  # noqa: E501
        (
            httpx.Response(200, json=_completion("Qwen3.8-27B", "", "length")),
            GenerationStatus.INVALID_RESPONSE,
            "truncated",
        ),
        (
            httpx.Response(200, json=_completion("Qwen3.8-27B", None)),
            GenerationStatus.INVALID_RESPONSE,
            "empty_content",
        ),
        (
            httpx.Response(200, json=_completion("Qwen3.8-27B", "<thought>The answer is", "length")),  # noqa: E501
            GenerationStatus.INVALID_RESPONSE,
            "truncated",
        ),
        (
            httpx.Response(200, json=_completion("some-other-model", "hi")),
            GenerationStatus.MODEL_MISMATCH,
            "served_model_mismatch",
        ),
    ],
)
async def test_failures_are_normalized(response, status, code) -> None:
    result = await _adapter(lambda request: response).generate(
        GenerationRequest(model_id="ovh/qwen", prompt="hi")
    )
    assert (result.status, result.error_code) == (status, code)
    assert result.error_message


@pytest.mark.asyncio
async def test_truncated_answers_keep_their_billed_cost(monkeypatch) -> None:
    monkeypatch.setenv("TEST_NIM_KEY", "k")
    body = _completion("deepseek-ai/deepseek-v4.1-flash", "", "length")
    result = await _adapter(lambda request: httpx.Response(200, json=body)).generate(
        GenerationRequest(model_id="nim/deepseek", prompt="hi")
    )
    assert (result.status, result.error_code) == (GenerationStatus.INVALID_RESPONSE, "truncated")
    assert result.cost_usd == Decimal("0.0002")
    assert result.completion_tokens == 50


@pytest.mark.asyncio
async def test_inline_thought_block_is_removed_before_scoring() -> None:
    content = "<thought>Maybe the answer is (C).\nNo: (H).</thought>The answer is (H)"
    result = await _adapter(
        lambda request: httpx.Response(200, json=_completion("Qwen3.8-27B", content))
    ).generate(GenerationRequest(model_id="ovh/qwen", prompt="hi"))
    assert (result.status, result.text) == (GenerationStatus.SUCCESS, "The answer is (H)")


@pytest.mark.asyncio
async def test_timeouts_and_network_errors_are_reported_not_raised() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    request = GenerationRequest(model_id="ovh/qwen", prompt="hi")
    assert (await _adapter(timeout).generate(request)).status == GenerationStatus.TIMEOUT
    network = await _adapter(refused).generate(request)
    assert (network.status, network.error_code) == (GenerationStatus.PROVIDER_ERROR, "ConnectError")


@pytest.mark.asyncio
async def test_request_options_pin_hosts_and_reported_cost_wins() -> None:
    pinned = Endpoint(
        "or/gemma",
        "openrouter",
        "https://or.test/api/v1",
        "google/gemma-4-26b-a4b-it",
        prompt_price=Decimal("0.0000001"),
        completion_price=Decimal("0.0000003"),
        api_key_env="OPENROUTER_API_KEY",
        request_options={"provider": {"order": ["nextbit/bf16"], "allow_fallbacks": False}},
    )
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(
            {"body": json.loads(request.content), "auth": request.headers.get("authorization")}
        )
        body = _completion("google/gemma-4-26b-a4b-it", "ok")
        body["provider"] = "NextBit"
        body["usage"]["cost"] = 0.0000123
        return httpx.Response(200, json=body)

    adapter = OpenAICompatibleAdapter(
        [pinned], transport=httpx.MockTransport(handler), keys={"OPENROUTER_API_KEY": "k"}
    )
    result = await adapter.generate(GenerationRequest(model_id="or/gemma", prompt="hi"))
    assert seen[0]["body"]["provider"] == {"order": ["nextbit/bf16"], "allow_fallbacks": False}
    assert seen[0]["body"]["model"] == "google/gemma-4-26b-a4b-it"
    assert seen[0]["auth"] == "Bearer k"
    assert result.provider == "openrouter:NextBit"
    assert (result.cost_usd, result.cost_source) == (Decimal("0.0000123"), CostSource.PROVIDER)


@pytest.mark.asyncio
async def test_served_model_comparison_tolerates_provider_spellings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion("models/qwen3.8-27b:latest", "ok"))

    result = await _adapter(handler).generate(GenerationRequest(model_id="ovh/qwen", prompt="hi"))
    assert result.status == GenerationStatus.SUCCESS
