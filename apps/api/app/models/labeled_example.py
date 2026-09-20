"""LabeledExample records.

Stored immutably, like Ruling, and enforced by the same kind of trigger. Every
reviewer decision becomes one of these; they are what Phase 2 is built from, and
the Phase 1 exit metric counts them.

Derived from a Ruling rather than from ChecklistItem.resolved_by, so a
correction cannot silently rewrite training data that already exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import UUIDPrimaryKeyMixin
from app.models.enums import Verdict


class LabeledExample(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "labeled_example"
    __table_args__ = (
        UniqueConstraint("ruling_id", name="uq_labeled_example_ruling"),
        CheckConstraint(
            "human_verdict IN ('pass', 'fail')",
            name="ck_labeled_example_verdict_is_definite",
        ),
        Index("ix_labeled_example_item_type", "item_type"),
        Index("ix_labeled_example_reviewer", "reviewer_id"),
    )

    ruling_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ruling.id", ondelete="RESTRICT"), nullable=False
    )
    checklist_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checklist_item.id", ondelete="RESTRICT"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment=(
            "Copied from the checklist item. No foreign key: requirement identity is "
            "(id, ruleset_version) and the checklist item already guarantees integrity."
        ),
    )
    evidence_ids: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    item_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="The grouping calibration and golden sets are computed per.",
    )
    grader_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="The full grader record. Null throughout Phase 1."
    )
    human_verdict: Mapped[Verdict] = mapped_column(
        pg_enum(Verdict, "verdict"),
        nullable=False,
        comment=(
            "Always pass or fail. A labelled example is a definite judgement about the "
            "installation, so the indeterminate verdicts cannot produce one: a recapture "
            "judges the photograph, and a grader that could not tell has nothing to teach."
        ),
    )
    human_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    labeled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        comment=(
            "A reviewer label weighs 1.0. The tech's predict-then-reveal call is "
            "stored as a second label with lower weight in Phase 2."
        ),
    )
