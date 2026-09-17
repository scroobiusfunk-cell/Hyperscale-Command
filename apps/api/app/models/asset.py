"""Asset records and their tag aliases.

`aliases` is a child table rather than a text[] column. The architecture doc
lists it as text[], but the reconciler has to look assets up *by* alias and
record which source each variant came from, and neither is workable inside an
array. The ORM attribute keeps the name the doc uses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AliasSource, ReconciliationStatus


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset"
    __table_args__ = (
        UniqueConstraint("project_id", "tag", name="uq_asset_project_tag"),
        Index("ix_asset_project_equipment_class", "project_id", "equipment_class"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="RESTRICT"), nullable=False
    )
    tag: Mapped[str] = mapped_column(String(200), nullable=False)
    equipment_class: Mapped[str] = mapped_column(String(64), nullable=False)
    system: Mapped[str] = mapped_column(String(200), nullable=False)

    # location: room, grid ref, model coordinates
    location_room: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location_grid_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_model_x: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    location_model_y: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    location_model_z: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)

    parent_asset: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id", ondelete="SET NULL"), nullable=True
    )
    cxalloy_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(
        pg_enum(ReconciliationStatus, "reconciliation_status"), nullable=False
    )

    aliases: Mapped[list[AssetAlias]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )


class AssetAlias(UUIDPrimaryKeyMixin, Base):
    """Every tag variant seen across sources.

    `value` is what the source actually said; `normalized_value` is what the
    reconciler matches on. Both are kept so a match can be audited against the
    source rather than against our normalization of it.
    """

    __tablename__ = "asset_alias"
    __table_args__ = (
        UniqueConstraint("asset_id", "value", "source", name="uq_asset_alias_value_source"),
        Index("ix_asset_alias_normalized_value", "normalized_value"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[AliasSource] = mapped_column(
        pg_enum(AliasSource, "alias_source"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="aliases")


class AssetSubmittal(Base):
    """Approved submittals governing an asset (Asset.submittal_ids)."""

    __tablename__ = "asset_submittal"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
    )
    submittal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_document.id", ondelete="RESTRICT"),
        primary_key=True,
    )
