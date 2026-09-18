"""The field app's event log, as received by the server.

"Captures are written to local storage with a client-generated id and an event
log... On reconnect the event log syncs in order; the server applies events
idempotently by client id, so a retried upload never duplicates evidence."

Every event is stored before it is applied, and stored whether or not it can be
applied. A rejected event is a row saying why, not a dropped packet: a tech who
walked a building and lost half of it to a silent parse failure will not walk it
again on trust.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import UUIDPrimaryKeyMixin


class SyncEventType(StrEnum):
    ITEM_OPENED = "item_opened"
    """The tech looked at the item. Kept for time-on-item, not for state."""

    CAPTURE_TAKEN = "capture_taken"
    GATE_FAILED = "gate_failed"
    """A capture the gate rejected and the tech retook. No evidence is stored,
    but the fact it happened is the Phase 1 evidence-quality signal."""

    ITEM_CAPTURED = "item_captured"
    """The tech considers the item's evidence complete."""

    ITEM_DEFERRED = "item_deferred"
    WALK_COMPLETED = "walk_completed"


class SyncEventStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    SUPERSEDED = "superseded"
    """A reviewer had already decided the item. The evidence is attached; the
    tech's state change is not applied."""

    REJECTED = "rejected"


class SyncEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_event"
    __table_args__ = (
        # The idempotency key. A retried upload of the same event is the normal
        # case on a bad connection, not an error.
        UniqueConstraint("client_event_id", name="uq_sync_event_client_event_id"),
        Index("ix_sync_event_walk_sequence", "client_walk_id", "sequence"),
        Index(
            "ix_sync_event_pending",
            "status",
            postgresql_where="status = 'pending'",
        ),
    )

    client_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_walk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monotonic per walk on the device. Replay order, because device clocks drift.",
    )
    event_type: Mapped[SyncEventType] = mapped_column(
        pg_enum(SyncEventType, "sync_event_type"), nullable=False
    )
    checklist_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Device clock. Not trusted for ordering."
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )

    status: Mapped[SyncEventStatus] = mapped_column(
        pg_enum(SyncEventStatus, "sync_event_status"),
        nullable=False,
        default=SyncEventStatus.PENDING,
    )
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
