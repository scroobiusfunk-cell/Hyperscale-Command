"""The learner's own call, recorded before they are shown the answer.

This is the record that turns the platform from a capture tool into a teaching
one. Without it there is nothing to compare a learner against: a checklist you
photograph measures photography, and only a judgement you committed to before
the reveal measures judgement.

Everything about this table exists to protect one property: **a prediction
cannot be changed, and cannot be created, after the answer is known.** If a
learner could adjust their call once the reviewer had ruled, every agreement
number computed from this table would be a flattering fiction. So:

- Rows are append-only, enforced by a database trigger, exactly like `Ruling`.
- One call per person per checklist item, enforced by a unique constraint.
- Replay refuses a prediction for an item that already carries a ruling. The
  device cannot backdate its way around that, because the server checks against
  its own record of what has been decided, not against the device's clock.

A recapture does not reopen the call. Being asked to retake a blurry photograph
says nothing about whether the installation was right, and a learner who has
already judged this asset has already had the lesson.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import UUIDPrimaryKeyMixin
from app.models.enums import PredictedVerdict


class Prediction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "prediction"
    __table_args__ = (
        UniqueConstraint("checklist_item_id", "predicted_by", name="uq_prediction_item_person"),
        Index("ix_prediction_person_created", "predicted_by", "created_at"),
        Index("ix_prediction_item", "checklist_item_id"),
    )

    checklist_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checklist_item.id", ondelete="RESTRICT"), nullable=False
    )
    predicted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    verdict: Mapped[PredictedVerdict] = mapped_column(
        pg_enum(PredictedVerdict, "predicted_verdict"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment=(
            "Which disqualifier the learner believes they saw, from the item's own "
            "short list. Null on a pass or when they were unsure."
        ),
    )
    note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Optional free text. Nothing depends on it."
    )
    #: The grouping agreement is reported per, copied at write time so that a
    #: later rule-set version cannot silently re-bucket a learner's history.
    item_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # No updated_at: this record is never updated.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
