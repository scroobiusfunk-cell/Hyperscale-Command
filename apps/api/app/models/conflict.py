"""Unresolved precedence conflicts.

"Conflicts that the rules cannot settle are surfaced, not resolved." This is
where they surface. A conflict means two documents govern the same check and the
precedence rules could not choose between them, so a person has to.

Modelled on the reconciliation queue for the same reason: something a person
must clear is a row with a status, not a log line nobody reads.
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


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    """No longer a conflict — the requirements changed underneath it."""


class RequirementConflict(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requirement_conflict"
    __table_args__ = (
        # One open conflict per check per rule set. Re-running precedence
        # resolution updates the row rather than stacking duplicates.
        Index(
            "uq_requirement_conflict_open",
            "rule_set_id",
            "check_key",
            unique=True,
            postgresql_where="status = 'open'",
        ),
        Index("ix_requirement_conflict_status", "status"),
        CheckConstraint(
            "status <> 'resolved' OR (resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_requirement_conflict_resolved_by_a_person",
        ),
    )

    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_set.id", ondelete="CASCADE"), nullable=False
    )
    check_key: Mapped[str] = mapped_column(String(300), nullable=False)
    reason: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Why the rules could not choose, in plain words."
    )
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment=(
            "The competing requirements and how they ranked, so the person sees what the rules saw."
        ),
    )
    status: Mapped[ConflictStatus] = mapped_column(
        pg_enum(ConflictStatus, "conflict_status"), nullable=False, default=ConflictStatus.OPEN
    )
    winner_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
