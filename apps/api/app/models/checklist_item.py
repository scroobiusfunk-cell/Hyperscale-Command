"""ChecklistItem records.

state, resolved_at and resolved_by are a denormalized projection of the newest
Ruling (see OPEN_QUESTIONS.md Q10). Rulings are the source of truth; these
columns exist so the reviewer queue can be read without a correlated subquery
per row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BlockedReason, ChecklistItemState, CxAlloyDeliveryState


class ChecklistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "checklist_item"
    __table_args__ = (
        # Items are generated lazily per area as the capture plan needs them.
        # Generating the same area twice must not produce duplicates.
        UniqueConstraint(
            "asset_id",
            "requirement_id",
            "ruleset_version",
            name="uq_checklist_item_asset_requirement_ruleset",
        ),
        CheckConstraint(
            "state NOT IN ('reviewer_passed', 'reviewer_failed') "
            "OR (resolved_by IS NOT NULL AND resolved_at IS NOT NULL AND reviewer IS NOT NULL)",
            name="ck_checklist_item_ruling_names_a_person",
        ),
        CheckConstraint(
            "state <> 'blocked' OR (blocked_reason IS NOT NULL AND blocked_at IS NOT NULL)",
            name="ck_checklist_item_blocked_has_reason",
        ),
        CheckConstraint(
            "cxalloy_delivery_state <> 'delivery_confirmed' "
            "OR (cxalloy_delivery_confirmed_by IS NOT NULL "
            "AND cxalloy_delivery_confirmed_at IS NOT NULL)",
            name="ck_checklist_item_delivery_confirmed_by_a_person",
        ),
        # Requirement identity is (id, ruleset_version); see the note on
        # Requirement. An item therefore points at one requirement *as it was in
        # the rule set that generated the item*, which is what makes a published
        # rule set immutable from the field's point of view.
        ForeignKeyConstraint(
            ["requirement_id", "ruleset_version"],
            ["requirement.id", "requirement.ruleset_version"],
            name="fk_checklist_item_requirement",
            ondelete="RESTRICT",
        ),
        Index("ix_checklist_item_state", "state"),
        Index("ix_checklist_item_reviewer_state", "reviewer", "state"),
        Index(
            "ix_checklist_item_undelivered",
            "cxalloy_delivery_state",
            postgresql_where="cxalloy_delivery_state IN ('pending_export', 'exported')",
        ),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id", ondelete="RESTRICT"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[ChecklistItemState] = mapped_column(
        pg_enum(ChecklistItemState, "checklist_item_state"), nullable=False
    )

    assigned_tech: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    reviewer: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )

    grader_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="Always null in Phase 1; no grader exists."
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )

    blocked_reason: Mapped[BlockedReason | None] = mapped_column(
        pg_enum(BlockedReason, "blocked_reason"), nullable=True
    )
    blocked_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cxalloy_delivery_state: Mapped[CxAlloyDeliveryState] = mapped_column(
        pg_enum(CxAlloyDeliveryState, "cxalloy_delivery_state"),
        nullable=False,
        default=CxAlloyDeliveryState.NOT_APPLICABLE,
    )
    export_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cxalloy_exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cxalloy_delivery_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cxalloy_delivery_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
