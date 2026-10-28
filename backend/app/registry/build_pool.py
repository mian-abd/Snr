"""Write the dated Checkpoint 3 pool snapshot (run once; the output file is committed).

    uv run --project backend python -m app.registry.build_pool

Prices, hosts, limits, and policies were checked on 2026-10-27 against the OpenRouter models and
endpoints API, the OVHcloud AI Endpoints model list, and the providers' docs.
"""

from __future__ import annotations

from decimal import Decimal

from app.config import REPOSITORY_ROOT
from app.registry.pool import Access, PoolModel, PoolSnapshot, models_sha256
from app.storage import atomic_write_json

SNAPSHOT_ID = "cp3-pool-2026-10-27"
OUTPUT = REPOSITORY_ROOT / "data" / "registry" / f"{SNAPSHOT_ID}.json"

OPENROUTER = "https://openrouter.ai/api/v1"
OVH = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"
AI_STUDIO = "https://generativelanguage.googleapis.com/v1beta/openai"
NIM = "https://integrate.api.nvidia.com/v1"
OLLAMA = "http://localhost:11434/v1"


def _pin(*hosts: str) -> dict[str, object]:
    # Only the listed upstream hosts, in order; never a silent fallback outside them. Each result
    # records which host actually served it.
    return {"provider": {"order": list(hosts), "allow_fallbacks": False}}


def _price(value: str) -> Decimal:
    return Decimal(value)


MODELS = [
    PoolModel(
        id="gemma-4-26b", display_name="Gemma 4 26B A4B", family="Google Gemma",
        open_weight=True, parameters="25.2B total / 3.8B active", access=Access.PAID,
        provider="openrouter", base_url=OPENROUTER, upstream_model="google/gemma-4-26b-a4b-it",
        api_key_env="OPENROUTER_API_KEY", prompt_price_per_token=_price("0.0000000765"),
        completion_price_per_token=_price("0.000000255"), context_length=262144,
        requests_per_minute=60, max_concurrency=3, request_options=_pin("nextbit/bf16"),
        data_policy="OpenRouter paid route pinned to NextBit (bf16).",
    ),
    PoolModel(
        id="mercury-3", display_name="Mercury 3", family="Inception (diffusion)",
        open_weight=False, parameters="undisclosed", access=Access.PAID, provider="openrouter",
        base_url=OPENROUTER, upstream_model="inception/mercury-3",
        api_key_env="OPENROUTER_API_KEY", prompt_price_per_token=_price("0.0000001"),
        completion_price_per_token=_price("0.00000035"), context_length=1000000,
        requests_per_minute=60, max_concurrency=3, request_options=_pin("inception"),
        data_policy="OpenRouter paid route; Inception is the only host.",
    ),
    PoolModel(
        id="gemini-4-argon", display_name="Gemini 4 Argon", family="Google Gemini",
        open_weight=False, parameters="undisclosed", access=Access.PAID, provider="openrouter",
        base_url=OPENROUTER, upstream_model="google/gemini-4-argon",
        api_key_env="OPENROUTER_API_KEY", prompt_price_per_token=_price("0.000002"),
        completion_price_per_token=_price("0.00001"), context_length=1048576,
        requests_per_minute=60, max_concurrency=3, request_options=_pin("google-ai-studio"),
        data_policy="OpenRouter paid route pinned to Google AI Studio (standard tier).",
    ),
    PoolModel(
        id="deepseek-v4-flash", display_name="DeepSeek V4 Flash", family="DeepSeek",
        open_weight=True, parameters="284B total / 13B active", access=Access.PAID,
        provider="openrouter", base_url=OPENROUTER, upstream_model="deepseek/deepseek-v4-flash",
        api_key_env="OPENROUTER_API_KEY", prompt_price_per_token=_price("0.00000014"),
        completion_price_per_token=_price("0.00000028"), context_length=1048576,
        requests_per_minute=40, max_concurrency=2,
        request_options=_pin("parasail/fp8", "crusoe/fp8", "deepinfra/fp8"),
        data_policy="OpenRouter paid route limited to three fp8 hosts (Parasail, Crusoe, "
        "DeepInfra); the serving host is recorded per call. Price is the highest of the three.",
    ),
    PoolModel(
        id="nemotron-3-ultra-free", display_name="Nemotron 3 Ultra 550B (free)",
        family="NVIDIA Nemotron", open_weight=True, parameters="550B total / 55B active",
        access=Access.FREE, provider="openrouter", base_url=OPENROUTER,
        upstream_model="nvidia/nemotron-3-ultra-550b-a55b:free", api_key_env="OPENROUTER_API_KEY",
        context_length=1000000, requests_per_minute=18, max_concurrency=2,
        data_policy="Free endpoint: NVIDIA logs prompts and may use them for training. Counts "
        "against the account-wide 1,000 free requests per day.",
    ),
    PoolModel(
        id="gpt-oss-120b", display_name="gpt-oss-120b", family="OpenAI gpt-oss",
        open_weight=True, parameters="117B total / 5.1B active", access=Access.FREE,
        provider="ovhcloud", base_url=OVH, upstream_model="gpt-oss-120b",
        context_length=131072, requests_per_minute=1.8, max_concurrency=2,
        data_policy="OVHcloud AI Endpoints anonymous access (2 requests/min per IP per model); "
        "OVHcloud states prompts are not stored or used for training.",
    ),
    PoolModel(
        id="llama-3.3-70b", display_name="Llama 3.3 70B Instruct", family="Meta Llama",
        open_weight=True, parameters="70B dense", access=Access.FREE, provider="ovhcloud",
        base_url=OVH, upstream_model="Meta-Llama-3_3-70B-Instruct", context_length=131072,
        requests_per_minute=1.8, max_concurrency=2,
        data_policy="OVHcloud AI Endpoints anonymous access; not stored or used for training.",
    ),
    PoolModel(
        id="qwen-3.8-27b", display_name="Qwen 3.8 27B", family="Alibaba Qwen",
        open_weight=True, parameters="27B dense", access=Access.FREE, provider="ovhcloud",
        base_url=OVH, upstream_model="Qwen3.8-27B", context_length=262144,
        requests_per_minute=1.8, max_concurrency=2,
        data_policy="OVHcloud AI Endpoints anonymous access; not stored or used for training.",
    ),
    PoolModel(
        id="gemma-4-31b", display_name="Gemma 4 31B", family="Google Gemma", open_weight=True,
        parameters="30.7B dense", access=Access.FREE, provider="google_ai_studio",
        base_url=AI_STUDIO, upstream_model="gemma-4-31b-it", api_key_env="GEMINI_API_KEY",
        context_length=262144, requests_per_minute=14, max_concurrency=1,
        data_policy="Google AI Studio free tier: Google may use prompts to improve its products.",
    ),
    PoolModel(
        id="deepseek-v4.1-flash", display_name="DeepSeek V4.1 Flash", family="DeepSeek",
        open_weight=True, parameters="552B total / 8-16B active", access=Access.FREE,
        provider="nvidia_nim", base_url=NIM, upstream_model="deepseek-ai/deepseek-v4.1-flash",
        api_key_env="NVIDIA_API_KEY", context_length=1000000, requests_per_minute=35,
        max_concurrency=2,
        data_policy="NVIDIA API Catalog developer trial (evaluation use).",
    ),
    PoolModel(
        id="qwen-3.5-9b-local", display_name="Qwen 3.5 9B (local)", family="Alibaba Qwen",
        open_weight=True, parameters="9B dense, Q4_K_M", access=Access.LOCAL, provider="ollama",
        base_url=OLLAMA, upstream_model="qwen3.5-9b-cp3", context_length=8192,
        requests_per_minute=600, max_concurrency=1,
        request_options={"reasoning_effort": "none"},
        data_policy="Runs on this laptop's RTX 5060 through Ollama; nothing leaves the machine.",
    ),
]


def main() -> int:
    snapshot = PoolSnapshot(
        snapshot_id=SNAPSHOT_ID,
        metadata_as_of="2026-10-27T00:00:00Z",
        models_sha256=models_sha256(MODELS),
        models=MODELS,
    )
    atomic_write_json(OUTPUT, snapshot)
    print(f"wrote {len(MODELS)} models to {OUTPUT.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
