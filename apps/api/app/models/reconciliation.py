"""The reconciliation queue.

The architecture doc calls the unresolved queue a leading indicator of trouble:
if it grows faster than someone clears it, the field is walking to wrong assets.
So the queue is a first-class table with its size as a tracked metric, not a
log line.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AliasSource


class ReconciliationQueueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReconciliationQueueReason(StrEnum):
    NO_MATCH = "no_match"
    LOW_CONFIDENCE = "low_confidence"
    AMBIGUOUS = "ambiguous"


class ReconciliationQueueItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reconciliation_queue_item"
    __table_args__ = (
        # One open row per observed tag per source. Re-importing the same
        # equipment list must not grow the queue.
        Index(
            "uq_reconciliation_queue_open_observation",
            "project_id",
            "normalized_tag",
            "source",
            unique=True,
            postgresql_where="status = 'open'",
        ),
        Index("ix_reconciliation_queue_status", "status"),
        CheckConstraint(
            "status <> 'resolved' OR (resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_reconciliation_queue_resolved_by_a_person",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="RESTRICT"), nullable=False
    )
    raw_tag: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Exactly what the source said."
    )
    normalized_tag: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[AliasSource] = mapped_column(
        pg_enum(AliasSource, "alias_source"), nullable=False
    )
    observed_equipment_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_location_room: Mapped[str | None] = mapped_column(String(200), nullable=True)

    reason: Mapped[ReconciliationQueueReason] = mapped_column(
        pg_enum(ReconciliationQueueReason, "reconciliation_queue_reason"), nullable=False
    )
    explanation: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Why the reconciler would not decide, in plain words."
    )
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="What the reconciler considered and how it scored, so the person sees what it saw.",
    )

    status: Mapped[ReconciliationQueueStatus] = mapped_column(
        pg_enum(ReconciliationQueueStatus, "reconciliation_queue_status"),
        nullable=False,
        default=ReconciliationQueueStatus.OPEN,
    )
    resolved_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id", ondelete="RESTRICT"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
