"""Evidence records.

Deliberately carries no verdict column of any kind. A judgment about evidence
lives on Ruling or GraderResult; leaving the column off means no future code can
write one here by accident.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EvidenceStatus, MediaType


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        # The idempotency key. Replaying the sync event log must never produce
        # a second row for the same capture.
        UniqueConstraint("client_id", name="uq_evidence_client_id"),
        CheckConstraint("byte_size > 0", name="ck_evidence_byte_size_positive"),
        CheckConstraint("step_index >= 0", name="ck_evidence_step_index_non_negative"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_evidence_content_hash_is_sha256"
        ),
        Index("ix_evidence_checklist_item", "checklist_item_id"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    checklist_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checklist_item.id", ondelete="RESTRICT"), nullable=False
    )
    capture_recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capture_recipe.id", ondelete="RESTRICT"), nullable=False
    )
    capture_recipe_version: Mapped[str] = mapped_column(String(20), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)

    media_type: Mapped[MediaType] = mapped_column(pg_enum(MediaType, "media_type"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Both clocks. Device clocks on a construction site drift, and an offline
    # walk can sit for days before it syncs; order anything that matters by
    # received_at.
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    captured_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    device_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    gate_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    retake_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[EvidenceStatus] = mapped_column(
        pg_enum(EvidenceStatus, "evidence_status"), nullable=False
    )
