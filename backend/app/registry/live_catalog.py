"""Check the learned router's pool against the providers' live catalogs (proposal, week of Nov 19).

The router was trained on the dated ``cp3-pool-2026-10-27`` snapshot, but providers keep changing:
on 2026-11-12 OpenRouter stopped serving Mercury 3 and cut Gemma 4 26B's price. At startup (and
on request) the server asks each provider what it serves now:

- OpenRouter: ``/api/v1/models/{model}/endpoints`` lists every host with its price. A model is
  unavailable when none of its pinned hosts serves it; its live price is the highest price among
  the pinned hosts that still do (the snapshot's rule).
- OVHcloud and Ollama: their OpenAI-compatible ``/models`` lists. A local model is unavailable
  when the Ollama server is not running.

Only a positive answer marks a model unavailable. A check that fails leaves the model as the
snapshot describes it, and when every check fails the whole status falls back to the snapshot.
The learned router treats an unavailable model as a failed hard requirement and scales expected
costs by the live price (``app.learned.router``); the model itself is not retrained.

    uv run --project backend python -m app.registry.live_catalog            # print the status
    uv run --project backend python -m app.registry.live_catalog --save PATH
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from app.domain.models import CatalogSource, LiveCatalogStatus, LiveModelStatus
from app.registry.pool import PoolModel, PoolSnapshot, load_pool

OPENROUTER_ENDPOINTS = "https://openrouter.ai/api/v1/models/{model}/endpoints"
REQUEST_TIMEOUT_SECONDS = 6.0
PROVIDER_NAMES = {"ovhcloud": "OVHcloud endpoint", "ollama": "local Ollama server"}


def _per_million(value: Any) -> float | None:
    try:
        return float(Decimal(str(value)) * 1_000_000)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _money(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"${value:.4f}".rstrip("0").rstrip(".") if value else "$0"


def _base(model: PoolModel, *, checked: bool, available: bool, note: str) -> LiveModelStatus:
    return LiveModelStatus(
        model_id=model.id,
        display_name=model.display_name,
        provider=model.provider,
        upstream_model=model.upstream_model,
        checked=checked,
        available=available,
        note=note,
        snapshot_prompt_price_per_million=float(model.prompt_price_per_token * 1_000_000),
        snapshot_completion_price_per_million=float(model.completion_price_per_token * 1_000_000),
    )


def _unchecked(model: PoolModel, reason: str) -> LiveModelStatus:
    return _base(model, checked=False, available=True, note=f"{reason}; using the snapshot")


def _pinned_hosts(model: PoolModel) -> list[str]:
    provider = model.request_options.get("provider") or {}
    return [str(tag) for tag in provider.get("order") or []]


def openrouter_status(model: PoolModel, response: httpx.Response) -> LiveModelStatus:
    """Interpret one ``/endpoints`` answer for a pool model."""
    if response.status_code == 404:
        return _base(
            model, checked=True, available=False,
            note=f"OpenRouter no longer lists {model.upstream_model} (retired)",
        )
    response.raise_for_status()
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("endpoints"), list):
        # Only a well-formed, empty host list is evidence that a model was retired.
        raise ValueError("unexpected endpoints response")
    endpoints = [item for item in data["endpoints"] if isinstance(item, dict)]
    if not endpoints:
        return _base(
            model, checked=True, available=False,
            note=f"OpenRouter lists {model.upstream_model} but no host serves it any more "
            "(retired)",
        )
    by_tag = {str(endpoint.get("tag")): endpoint for endpoint in endpoints}
    pinned = _pinned_hosts(model)

    def hosts_for(pin: str) -> list[str]:
        # An exact tag wins ("google-ai-studio" is the standard tier, not "/priority"); a bare
        # slug with no exact endpoint covers that provider's tagged ones ("inception/fp8").
        if pin in by_tag:
            return [pin]
        return [tag for tag in by_tag if tag.startswith(f"{pin}/")]

    serving = sorted({tag for pin in pinned for tag in hosts_for(pin)} if pinned else by_tag)
    missing = [pin for pin in pinned if not hosts_for(pin)]
    if not serving:
        status = _base(
            model, checked=True, available=False,
            note=f"None of the pinned hosts ({', '.join(pinned)}) serves "
            f"{model.upstream_model} any more",
        )
        return status.model_copy(update={"missing_hosts": missing})
    prompt_prices = [
        _per_million((by_tag[tag].get("pricing") or {}).get("prompt")) for tag in serving
    ]
    completion_prices = [
        _per_million((by_tag[tag].get("pricing") or {}).get("completion")) for tag in serving
    ]
    live_prompt = max((price for price in prompt_prices if price is not None), default=None)
    live_completion = max(
        (price for price in completion_prices if price is not None), default=None
    )
    status = _base(model, checked=True, available=True, note="")
    changes: list[str] = []
    if live_prompt is not None and live_completion is not None and (
        abs(live_prompt - status.snapshot_prompt_price_per_million) > 1e-9
        or abs(live_completion - status.snapshot_completion_price_per_million) > 1e-9
    ):
        changes.append(
            f"price changed from {_money(status.snapshot_prompt_price_per_million)} / "
            f"{_money(status.snapshot_completion_price_per_million)} to {_money(live_prompt)} / "
            f"{_money(live_completion)} per million input / output tokens"
        )
    if missing:
        changes.append(f"pinned host {', '.join(missing)} no longer serves it")
    served = "served by its pinned host" if pinned else "served on OpenRouter"
    note = "; ".join(changes) if changes else f"{served}; price unchanged"
    return status.model_copy(
        update={
            "note": note[0].upper() + note[1:],
            "live_prompt_price_per_million": live_prompt,
            "live_completion_price_per_million": live_completion,
            "serving_hosts": serving,
            "missing_hosts": missing,
        }
    )


def listed_status(model: PoolModel, listed: set[str]) -> LiveModelStatus:
    """Interpret an OpenAI-compatible ``/models`` list (OVHcloud, Ollama)."""
    where = PROVIDER_NAMES.get(model.provider, model.provider)
    names = {model.upstream_model, f"{model.upstream_model}:latest"}
    if names & listed:
        return _base(model, checked=True, available=True, note=f"Listed by the {where}")
    return _base(
        model, checked=True, available=False,
        note=f"The {where} no longer lists {model.upstream_model}",
    )


async def _openrouter(client: httpx.AsyncClient, model: PoolModel) -> LiveModelStatus:
    try:
        response = await client.get(OPENROUTER_ENDPOINTS.format(model=model.upstream_model))
        return openrouter_status(model, response)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        return _unchecked(model, f"OpenRouter check failed ({type(exc).__name__})")


async def _listing(
    client: httpx.AsyncClient, base_url: str, models: list[PoolModel]
) -> list[LiveModelStatus]:
    try:
        response = await client.get(f"{base_url.rstrip('/')}/models")
        response.raise_for_status()
        body = response.json()
        rows = body.get("data") if isinstance(body, dict) else None
        listed = {str(row.get("id")) for row in rows or [] if isinstance(row, dict)}
    except httpx.ConnectError as exc:
        if all(model.provider == "ollama" for model in models):
            # Nothing listens on the local port, so a call would fail too.
            return [
                _base(model, checked=True, available=False,
                      note="The local Ollama server is not running")
                for model in models
            ]
        return [_unchecked(model, f"Check failed ({type(exc).__name__})") for model in models]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        return [_unchecked(model, f"Check failed ({type(exc).__name__})") for model in models]
    return [listed_status(model, listed) for model in models]


async def check_live_catalog(
    models: Iterable[PoolModel],
    snapshot: PoolSnapshot,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    now: datetime | None = None,
) -> LiveCatalogStatus:
    """Ask each provider what it serves now; never raises for network failures."""
    ordered = sorted(models, key=lambda model: model.id)
    by_base: dict[str, list[PoolModel]] = {}
    jobs: list[Any] = []
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS, transport=transport,
        headers={"Accept": "application/json"},
    ) as client:
        for model in ordered:
            if model.provider == "openrouter":
                jobs.append(_openrouter(client, model))
            elif model.provider in PROVIDER_NAMES and not model.api_key_env:
                by_base.setdefault(model.base_url, []).append(model)
        jobs.extend(_listing(client, base, members) for base, members in by_base.items())
        results = await asyncio.gather(*jobs)
    found: dict[str, LiveModelStatus] = {}
    for result in results:
        for status in result if isinstance(result, list) else [result]:
            found[status.model_id] = status
    statuses = [
        found.get(model.id)
        or _unchecked(model, "This provider has no public catalog check")
        for model in ordered
    ]
    attempted = [
        status for status in statuses if status.note != (
            "This provider has no public catalog check; using the snapshot"
        )
    ]
    answered = [status for status in attempted if status.checked]
    error = None
    if attempted and not answered:
        error = "Every live catalog check failed; routing uses the dated snapshot"
    return LiveCatalogStatus(
        source=CatalogSource.LIVE if answered else CatalogSource.SNAPSHOT,
        pool_snapshot_id=snapshot.snapshot_id,
        snapshot_as_of=snapshot.metadata_as_of,
        checked_at_utc=now or datetime.now(UTC),
        error=error,
        models=statuses,
    )


def snapshot_status(snapshot: PoolSnapshot, *, error: str | None = None) -> LiveCatalogStatus:
    """The fallback when the check is disabled or could not run at all."""
    return LiveCatalogStatus(
        source=CatalogSource.SNAPSHOT if error else CatalogSource.OFF,
        pool_snapshot_id=snapshot.snapshot_id,
        snapshot_as_of=snapshot.metadata_as_of,
        error=error,
    )


def main() -> int:
    from app.config import REPOSITORY_ROOT
    from app.learned.router import ROUTER_MODEL_PATH, ROUTER_POOL_FILE, load_router

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--save", type=Path, help="Write the status as JSON to this path")
    args = parser.parse_args()
    snapshot = load_pool(REPOSITORY_ROOT / "data" / ROUTER_POOL_FILE)
    router = load_router(ROUTER_MODEL_PATH, snapshot)
    status = asyncio.run(check_live_catalog(router.models.values(), snapshot))
    for model in status.models:
        flag = "ok  " if model.available else "GONE"
        print(f"{flag} {model.model_id:24} {model.note}")
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(status.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.save}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
