"""Beacon web dashboard -- FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Beacon Dashboard",
        description="Personal ops agent web interface",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from src.web import routes  # noqa: PLC0415  (late import avoids circular)
    app.include_router(routes.router)

    from src.advanced import api as advanced_api  # noqa: PLC0415
    app.include_router(advanced_api.router, prefix="/api")

    from src.web import store_api  # noqa: PLC0415
    app.include_router(store_api.router, prefix="/api/store")

    return app
