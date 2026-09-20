"""GraderResult records.

Nothing writes one of these in Phase 1. The table exists so the shared output
contract is fixed before any grader exists to bend it, and so
ChecklistItem.grader_result_id has somewhere real to point.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import UUIDPrimaryKeyMixin
from app.models.enums import Verdict, VerdictReason


class GraderResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "grader_result"
    __table_args__ = (
        # The pairing is the whole point of the change: an indeterminate verdict
        # that does not say which kind it is tells nobody anything, and a pass
        # carrying a reason for being unsure is two contradictory claims in one
        # row. Refused at the storage layer, in all three tables.
        CheckConstraint(
            "(verdict = 'indeterminate') = (verdict_reason IS NOT NULL)",
            name="ck_grader_result_reason_iff_indeterminate",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_grader_result_confidence_range"
        ),
        # A grader that cannot tell must not also claim to be sure. This is the
        # confident-wrong-pass failure mode, blocked at the storage layer.
        CheckConstraint(
            "verdict <> 'indeterminate' OR confidence <= 0.5",
            name="ck_grader_result_insufficient_is_not_confident",
        ),
        CheckConstraint(
            "jsonb_array_length(evidence_used) > 0", name="ck_grader_result_cites_evidence"
        ),
    )

    checklist_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checklist_item.id", ondelete="RESTRICT"), nullable=False
    )
    verdict: Mapped[Verdict] = mapped_column(pg_enum(Verdict, "verdict"), nullable=False)
    verdict_reason: Mapped[VerdictReason | None] = mapped_column(
        pg_enum(VerdictReason, "verdict_reason"),
        nullable=True,
        comment=(
            "Which kind of indeterminate. Set exactly when verdict is indeterminate; a "
            "check constraint refuses the other combinations."
        ),
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_used: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    observed_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    expected_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    grader_id: Mapped[str] = mapped_column(String(100), nullable=False)
    grader_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
