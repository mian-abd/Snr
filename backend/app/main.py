from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app import __version__
from app.api import router
from app.config import Settings, get_settings
from app.state import AppServices, build_services

# The build names every file under /assets after its content (index-DwCnFOow.js), so a file
# with a hash in its name never changes and a browser can keep it for a year.
_HASHED_NAME = re.compile(r"-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")
IMMUTABLE = "public, max-age=31536000, immutable"


class HashedAssets(StaticFiles):
    """Static files that tell browsers to cache hashed build output for good."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            hashed = _HASHED_NAME.search(path) is not None
            response.headers["Cache-Control"] = IMMUTABLE if hashed else "no-cache"
        return response


def create_app(
    *, settings: Settings | None = None, services: AppServices | None = None
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services or build_services(resolved_settings)
        await app.state.services.refresh_catalog()
        yield

    app = FastAPI(
        title="Adaptive LLM Router",
        version=__version__,
        description="Route prompts to a model that is good enough, with the evaluation behind it",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    # The reports and the prompt explorer are repetitive JSON; compressed, they shrink tenfold.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.include_router(router)

    dist = resolved_settings.frontend_dist_dir
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", HashedAssets(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend(full_path: str) -> Response:
        index = dist / "index.html"
        if index.exists():
            # The page names the current hashed files, so it must be checked on every visit.
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse(
            {
                "name": "Adaptive LLM Router",
                "message": "Frontend build not found. Run npm run build in frontend/.",
                "docs": "/docs",
            }
        )

    return app


app = create_app()
