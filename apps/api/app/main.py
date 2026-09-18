"""FastAPI application entrypoint.

Scaffold only: health and readiness. Subsystem routers are mounted here as
they land.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import curation, evidence, exports, field, reference, review
from app.config import Settings, load_settings
from app.db import build_session_factory
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
    if resolved.is_development or resolved.environment.value == "test":
        # The console runs on its own origin in development. Deployed
        # environments serve both from one origin and need no exception.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.state.settings = resolved
    app.state.session_factory = build_session_factory(resolved)
    app.include_router(curation.router)
    app.include_router(evidence.router)
    app.include_router(field.router)
    app.include_router(exports.router)
    app.include_router(reference.router)
    app.include_router(review.router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        """Liveness. Answers without touching any dependency."""
        return {"status": "ok"}

    return app


app = create_app()
