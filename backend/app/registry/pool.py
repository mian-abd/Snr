"""The Checkpoint 3 multi-provider model pool.

Unlike the Checkpoint 1/2 registries (OpenRouter only), each pool entry says how to reach the
model: an OpenAI-compatible base URL, the upstream model name, the environment variable that holds
its key (or none), request options such as a pinned OpenRouter upstream host, a pacing limit, and
the data policy that applies. The file is dated and checksummed like the other registries.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from app.domain.models import StrictModel
from app.providers.openai_compatible import Endpoint


class Access(StrEnum):
    PAID = "paid"
    FREE = "free"
    LOCAL = "local"


class PoolModel(StrictModel):
    id: str
    display_name: str
    family: str
    open_weight: bool
    parameters: str
    access: Access
    provider: str
    base_url: str
    upstream_model: str
    api_key_env: str | None = None
    prompt_price_per_token: Decimal = Decimal("0")
    completion_price_per_token: Decimal = Decimal("0")
    context_length: int
    requests_per_minute: float = Field(gt=0)
    max_concurrency: int = Field(default=1, ge=1, le=8)
    request_options: dict[str, Any] = Field(default_factory=dict)
    data_policy: str
    enabled: bool = True


class PoolSnapshot(StrictModel):
    schema_version: str = "1.0"
    snapshot_id: str
    metadata_as_of: str
    models_sha256: str
    models: list[PoolModel]


def models_sha256(models: list[PoolModel]) -> str:
    payload = [model.model_dump(mode="json") for model in models]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def load_pool(path: Path) -> PoolSnapshot:
    snapshot = PoolSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    ids = [model.id for model in snapshot.models]
    if len(ids) != len(set(ids)):
        raise ValueError("Pool contains duplicate model IDs")
    if models_sha256(snapshot.models) != snapshot.models_sha256:
        raise ValueError("Pool checksum does not match its model records")
    for model in snapshot.models:
        if model.access != Access.PAID and (
            model.prompt_price_per_token or model.completion_price_per_token
        ):
            raise ValueError(f"{model.id} is {model.access} but has a nonzero price")
    return snapshot


def endpoint_for(model: PoolModel) -> Endpoint:
    return Endpoint(
        model_id=model.id,
        provider=model.provider,
        base_url=model.base_url,
        upstream_model=model.upstream_model,
        prompt_price=model.prompt_price_per_token,
        completion_price=model.completion_price_per_token,
        api_key_env=model.api_key_env,
        request_options=model.request_options,
    )
