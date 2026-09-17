"""Rule set versions.

"A spec revision produces a new version and a diff, not a silent overwrite."
A RuleSet is that version: requirements belong to one, checklist items record
which one generated them, and publishing is a person's act with their name on it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class RuleSetStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


class RuleSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rule_set"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_rule_set_project_version"),
        CheckConstraint(
            "status <> 'published' OR (published_by IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_rule_set_published_by_a_person",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[RuleSetStatus] = mapped_column(
        pg_enum(RuleSetStatus, "rule_set_status"), nullable=False, default=RuleSetStatus.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_set.id", ondelete="RESTRICT"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
