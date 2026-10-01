from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from app.domain.models import ModelSpec, RegistrySnapshot

PINNED_MODEL_IDS = (
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
)


def canonical_models_sha256(models: list[ModelSpec] | list[dict[str, Any]]) -> str:
    payload = [
        model.model_dump(mode="json") if isinstance(model, ModelSpec) else model
        for model in models
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RegistryError(RuntimeError):
    pass


class ModelDriftError(RegistryError):
    pass


class ModelRegistry:
    def __init__(self, snapshot_path: Path) -> None:
        self.snapshot_path = snapshot_path
        self.snapshot = self._load()
        self._by_id = {model.id: model for model in self.snapshot.models}

    def _load(self) -> RegistrySnapshot:
        if not self.snapshot_path.exists():
            raise RegistryError(f"Registry snapshot not found: {self.snapshot_path}")
        snapshot = RegistrySnapshot.model_validate_json(
            self.snapshot_path.read_text(encoding="utf-8")
        )
        ids = [model.id for model in snapshot.models]
        if len(ids) != len(set(ids)):
            raise RegistryError("Registry contains duplicate model IDs")
        if tuple(ids) != PINNED_MODEL_IDS:
            raise RegistryError("Registry must contain the two pinned models in canonical order")
        actual_hash = canonical_models_sha256(snapshot.models)
        if actual_hash != snapshot.models_sha256:
            raise RegistryError("Registry checksum does not match its model records")
        return snapshot

    @property
    def models(self) -> list[ModelSpec]:
        return list(self.snapshot.models)

    def get(self, model_id: str) -> ModelSpec:
        try:
            return self._by_id[model_id]
        except KeyError as exc:
            raise RegistryError(f"Unknown model: {model_id}") from exc

    async def validate_live_catalog(self, api_key: str | None = None) -> None:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(self.snapshot.source_url, headers=headers)
            response.raise_for_status()
        rows = response.json().get("data", [])
        live_by_id = {row.get("id"): row for row in rows}
        for frozen in self.models:
            live = live_by_id.get(frozen.id)
            if live is None:
                raise ModelDriftError(f"Pinned model unavailable: {frozen.id}")
            architecture = live.get("architecture") or {}
            output_modalities = architecture.get("output_modalities") or []
            if "text" not in output_modalities:
                raise ModelDriftError(f"Pinned model no longer supports text output: {frozen.id}")
            pricing = live.get("pricing") or {}
            if str(pricing.get("prompt")) not in {"0", "0.0", "0.00000000"}:
                raise ModelDriftError(f"Pinned model is no longer free: {frozen.id}")
            if str(pricing.get("completion")) not in {"0", "0.0", "0.00000000"}:
                raise ModelDriftError(f"Pinned model is no longer free: {frozen.id}")
            if int(live.get("context_length") or 0) != frozen.context_length:
                raise ModelDriftError(
                    f"Context length drift for {frozen.id}: "
                    f"{live.get('context_length')} != {frozen.context_length}"
                )
