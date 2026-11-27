from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.state import AppServices


def _client(tmp_path: Path, registry, paid_registry) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>site</title>", encoding="utf-8")
    (dist / "assets" / "index-DwCnFOow.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "assets" / "inter-latin-wght-normal-Dx4kXJAl.woff2").write_bytes(b"font")
    (dist / "assets" / "plain.txt").write_text("not hashed", encoding="utf-8")
    settings = Settings(openrouter_api_key=None, data_dir=tmp_path, frontend_dist_dir=dist)
    services = AppServices(
        settings=settings,
        registry=registry,
        generation_service=None,
        benchmark_runner=None,
        routing_registry=paid_registry,
    )
    return TestClient(create_app(settings=settings, services=services))


def test_hashed_assets_are_cached_for_a_year_and_the_page_is_always_rechecked(
    tmp_path, registry, paid_registry
) -> None:
    with _client(tmp_path, registry, paid_registry) as client:
        script = client.get("/assets/index-DwCnFOow.js")
        assert script.status_code == 200
        assert script.headers["cache-control"] == "public, max-age=31536000, immutable"
        font = client.get("/assets/inter-latin-wght-normal-Dx4kXJAl.woff2")
        assert font.headers["cache-control"] == "public, max-age=31536000, immutable"

        index = client.get("/")
        assert index.status_code == 200
        assert index.headers["cache-control"] == "no-cache"
        # Every other path serves the same page, with the same rule.
        assert client.get("/some/route").headers["cache-control"] == "no-cache"


def test_an_unhashed_asset_is_not_cached_as_immutable(tmp_path, registry, paid_registry) -> None:
    with _client(tmp_path, registry, paid_registry) as client:
        assert client.get("/assets/plain.txt").headers["cache-control"] == "no-cache"


def test_a_revalidated_hashed_asset_keeps_its_cache_header(
    tmp_path, registry, paid_registry
) -> None:
    with _client(tmp_path, registry, paid_registry) as client:
        first = client.get("/assets/index-DwCnFOow.js")
        again = client.get(
            "/assets/index-DwCnFOow.js", headers={"If-None-Match": first.headers["etag"]}
        )
        assert again.status_code == 304
        assert again.headers["cache-control"] == "public, max-age=31536000, immutable"
