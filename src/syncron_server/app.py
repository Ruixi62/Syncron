"""Fabrique de l'application FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from syncron_core import APP_NAME, __version__
from syncron_core.errors import AppError
from syncron_server.catalog_store import CatalogValidationError
from syncron_server.config import Settings
from syncron_server.db import Database
from syncron_server.discord import DiscordOAuth, DiscordProvider
from syncron_server.protection import AuthRateLimit, BodySizeLimit
from syncron_server.routers import admin, auth, calendar, catalog, craft_admin, inbox, research
from syncron_server.schemas import IssueOut


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    discord: DiscordProvider | None = None,
) -> FastAPI:
    settings = settings or Settings()
    database = database or Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await database.dispose()

    app = FastAPI(
        title=f"{APP_NAME} API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.db = database
    app.state.discord = discord or DiscordOAuth(
        settings.discord_client_id, settings.discord_client_secret.get_secret_value()
    )
    app.state.catalog_cache = catalog.CatalogCache()

    @app.exception_handler(CatalogValidationError)
    async def _validation(_request: Request, exc: CatalogValidationError) -> JSONResponse:
        issues = [IssueOut.of(issue).model_dump() for issue in exc.issues]
        return JSONResponse({"detail": str(exc), "issues": issues}, status_code=422)

    @app.exception_handler(AppError)
    async def _business(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(AuthRateLimit, limit=lambda: app.state.settings.auth_rate_limit)
    app.add_middleware(BodySizeLimit, limit=lambda: app.state.settings.max_request_bytes)

    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(admin.router)
    app.include_router(craft_admin.router)
    for module in (research, calendar, inbox):
        app.include_router(module.router)
        app.include_router(module.admin_router)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
    return app
