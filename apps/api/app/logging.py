"""Structured logging.

CLAUDE.md requires every external call (LLM, CxAlloy, storage) to be logged
with a structured record including version and latency. `external_call` is
the single helper that does it, so the shape stays consistent and the eval
harness has one thing to parse.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog


def configure_logging(log_level: str = "INFO", *, json_output: bool = True) -> None:
    logging.basicConfig(format="%(message)s", level=getattr(logging, log_level.upper()))

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper())),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]


@contextmanager
def external_call(
    service: str,
    operation: str,
    *,
    version: str,
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    """Log one call to something outside this process.

    Yields a mutable dict; anything put in it is merged into the completion
    record. Latency and outcome are recorded either way, including on failure,
    because a provider that starts timing out is a drift signal.

        with external_call("cxalloy", "fetch_equipment", version="v2") as record:
            response = client.get(...)
            record["item_count"] = len(response.items)
    """
    log = get_logger("external_call")
    extra: dict[str, Any] = {}
    started = time.perf_counter()
    try:
        yield extra
    except Exception as exc:
        log.error(
            "external_call.failed",
            service=service,
            operation=operation,
            version=version,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
            **fields,
            **extra,
        )
        raise
    else:
        log.info(
            "external_call.completed",
            service=service,
            operation=operation,
            version=version,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            **fields,
            **extra,
        )
