"""What good looks like, and what wrong looks like.

A requirement written in words tells a learner what to verify. It does not tell
them what it looks like, and that is most of what a green inspector is missing.
"The arc flash label is legible from standing position" is unambiguous as a
sentence and useless as a mental image until you have seen fifty of them.

So each kind of check carries examples: at least one correct install, and — more
valuable — the near-misses. The obvious failures teach nothing. A plate that is
fitted but not seated, a label readable up close and unreadable from two metres,
is the thing a learner walks past.

Scoped by `item_type`, the same grouping used for calibration and golden sets, so
an example follows the *kind* of check rather than one asset, and survives a new
rule-set version.

The best source is usually the project's own work: a reviewer who has just
passed a textbook example can promote that photograph into a reference with one
action, and `sourced_from_evidence_id` records where it came from. That keeps the
teaching material in the same building and the same make of equipment the
learner is standing in front of.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ReferenceKind


class ReferenceImage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reference_image"
    __table_args__ = (
        CheckConstraint("byte_size > 0", name="ck_reference_image_byte_size_positive"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_reference_image_content_hash_is_sha256"
        ),
        CheckConstraint("length(btrim(caption)) > 0", name="ck_reference_image_caption_present"),
        Index("ix_reference_image_lookup", "project_id", "item_type", "kind"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    #: The kind of check this illustrates, not one asset.
    item_type: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[ReferenceKind] = mapped_column(
        pg_enum(ReferenceKind, "reference_kind"), nullable=False
    )
    caption: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "What to notice, in plain words. An example with no caption is a "
            "photograph; with one it is a lesson. Required for that reason."
        ),
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Lower sorts first, so a curator can put the clearest example in front.
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Set when a reviewer promoted a real capture into teaching material.
    sourced_from_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True
    )
    added_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
