"""Ruling records — append-only.

CLAUDE.md: "Reviewer rulings on safety items are append-only. Corrections are
new rulings." ChecklistItem cannot express that; it has one mutable resolved_by.
A Ruling row is never updated and never deleted, which is enforced by a database
trigger created in the migration rather than by convention here.

A `recapture_requested` ruling is a judgment on the evidence, not on the
installation, so it produces no LabeledExample.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import UUIDPrimaryKeyMixin
from app.models.enums import Verdict, VerdictReason


class Ruling(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ruling"
    __table_args__ = (
        # The pairing is the whole point of the change: an indeterminate verdict
        # that does not say which kind it is tells nobody anything, and a pass
        # carrying a reason for being unsure is two contradictory claims in one
        # row. Refused at the storage layer, in all three tables.
        CheckConstraint(
            "(verdict = 'indeterminate') = (verdict_reason IS NOT NULL)",
            name="ck_ruling_reason_iff_indeterminate",
        ),
        Index("ix_ruling_checklist_item_created", "checklist_item_id", "created_at"),
        Index("ix_ruling_reviewer_created", "reviewer_id", "created_at"),
    )

    checklist_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checklist_item.id", ondelete="RESTRICT"), nullable=False
    )
    verdict: Mapped[Verdict] = mapped_column(pg_enum(Verdict, "verdict"), nullable=False)
    verdict_reason: Mapped[VerdictReason | None] = mapped_column(
        pg_enum(VerdictReason, "verdict_reason"),
        nullable=True,
        comment=(
            "`recapture_requested` where a reviewer is sending the photograph back. That "
            "is a judgement on the evidence, not the installation, so it produces no "
            "LabeledExample and the item reopens."
        ),
    )
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "The reviewer's one-line note. Ruling and note are one action in the "
            "console; the flywheel starves if reviewers clear items silently."
        ),
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    supersedes: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ruling.id", ondelete="RESTRICT"),
        nullable=True,
        comment="A correction points at the ruling it replaces. Both stay readable.",
    )
    # No updated_at: this record is never updated.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
