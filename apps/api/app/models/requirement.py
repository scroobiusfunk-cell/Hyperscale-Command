"""Requirement records. Field names are verbatim from ARCHITECTURE.md section 1."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Criticality, RequirementStatus, VerificationMethod


class Requirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requirement"
    __table_args__ = (
        CheckConstraint(
            "criticality <> 'safety' OR char_length(why_it_matters) >= 20",
            name="ck_requirement_safety_has_real_reason",
        ),
        CheckConstraint(
            "status <> 'approved' OR jsonb_array_length(evidence_spec) > 0",
            name="ck_requirement_approved_has_evidence_spec",
        ),
        CheckConstraint("precedence_rank >= 0", name="ck_requirement_precedence_rank_non_negative"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="RESTRICT"), nullable=False
    )

    # applies_to, flattened. The three parts are queried independently during
    # instantiation, so they are columns rather than a JSONB blob.
    applies_to_equipment_class: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    applies_to_system: Mapped[str | None] = mapped_column(String(200), nullable=True)
    applies_to_location_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    statement: Mapped[str] = mapped_column(Text, nullable=False)
    verification_method: Mapped[VerificationMethod] = mapped_column(
        pg_enum(VerificationMethod, "verification_method"), nullable=False
    )
    evidence_spec: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    pass_criteria: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    criticality: Mapped[Criticality] = mapped_column(
        pg_enum(Criticality, "criticality"), nullable=False
    )

    # source: doc id, clause, page
    source_doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_document.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_clause: Mapped[str] = mapped_column(String(200), nullable=False)
    source_page: Mapped[int] = mapped_column(Integer, nullable=False)

    precedence_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequirementStatus] = mapped_column(
        pg_enum(RequirementStatus, "requirement_status"), nullable=False
    )
    ruleset_version: Mapped[str] = mapped_column(String(20), nullable=False)
