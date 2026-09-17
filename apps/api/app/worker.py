"""Celery application.

Grading, calibration, export generation, and detector training all run async
per the architecture doc. Phase 1 uses it for the CxAlloy results export queue
only; no tasks are registered yet.
"""

from __future__ import annotations

from celery import Celery

from app.config import load_settings


def create_celery() -> Celery:
    settings = load_settings()
    celery = Celery("fie", broker=settings.redis_url, backend=settings.redis_url)
    celery.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        timezone="UTC",
        enable_utc=True,
    )
    return celery


celery_app = create_celery()
