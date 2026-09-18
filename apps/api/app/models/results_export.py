"""A results export: one package of rulings for a person to import into CxAlloy.

The API is read only, so this is how a ruling reaches the system of record. The
queue, the retries and the delivery states are all still here — only the
terminal action changed, from a write to a file somebody carries across.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ExportStatus(StrEnum):
    PENDING = "pending"
    RENDERED = "rendered"
    DELIVERY_CONFIRMED = "delivery_confirmed"
    FAILED = "failed"


class ResultsExport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "results_export"
    __table_args__ = (
        Index("ix_results_export_project_status", "project_id", "status"),
        CheckConstraint(
            "status <> 'delivery_confirmed' "
            "OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_results_export_confirmed_by_a_person",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ExportStatus] = mapped_column(
        pg_enum(ExportStatus, "export_status"), nullable=False, default=ExportStatus.PENDING
    )
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "sha256 of the manifest. Rendering the same rulings twice produces the same "
            "hash, so a re-import is recognisable as a duplicate."
        ),
    )
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Failed items in this package. They alarm sooner than passes do.",
    )

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Only a person can confirm a ruling reached CxAlloy. The platform cannot.",
    )
