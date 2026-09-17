"""FastAPI application entrypoint.

Scaffold only: health and readiness. Subsystem routers are mounted here as
they land.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, load_settings
from app.logging import configure_logging, get_logger

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    configure_logging(resolved.log_level, json_output=not resolved.is_development)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("api.startup", environment=resolved.environment.value)
        yield
        log.info("api.shutdown")

    app = FastAPI(
        title="Field Inspection Engine API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        """Liveness. Answers without touching any dependency."""
        return {"status": "ok"}

    return app


app = create_app()
