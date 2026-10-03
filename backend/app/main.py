from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import router
from app.config import Settings, get_settings
from app.state import AppServices, build_services


def create_app(
    *, settings: Settings | None = None, services: AppServices | None = None
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services or build_services(resolved_settings)
        yield

    app = FastAPI(
        title="Adaptive LLM Router",
        version=__version__,
        description="Checkpoint 2 transparent routing over a reproducible model benchmark API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)

    dist = resolved_settings.frontend_dist_dir
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend(full_path: str) -> Response:
        index = dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            {
                "name": "Adaptive LLM Router",
                "checkpoint": 2,
                "message": "Frontend build not found. Run npm run build in frontend/.",
                "docs": "/docs",
            }
        )

    return app


app = create_app()
