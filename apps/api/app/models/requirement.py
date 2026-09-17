"""Requirement records. Field names are verbatim from ARCHITECTURE.md section 1."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin
from app.models.enums import Criticality, RequirementStatus, VerificationMethod


class Requirement(TimestampMixin, Base):
    __tablename__ = "requirement"
    __table_args__ = (
        CheckConstraint(
            "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_requirement_approved_by_a_person",
        ),
        # The architecture doc says Requirement.id is "stable across versions
        # where the requirement is unchanged". That makes id alone the wrong
        # primary key: a spec revision produces a new rule set carrying the same
        # requirement, so identity is (id, ruleset_version). ChecklistItem
        # already records both, so its foreign key is composite too.
        PrimaryKeyConstraint("id", "ruleset_version", name="pk_requirement"),
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        comment=(
            "Carried forward unchanged into a new rule set version when the "
            "requirement did not change."
        ),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="RESTRICT"), nullable=False
    )
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_set.id", ondelete="RESTRICT"), nullable=False
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

    check_key: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
        comment=(
            "What this requirement checks, normalized. Two requirements sharing a check_key "
            "are competing to govern the same check and go through precedence resolution "
            "together. Computed at compile time; a curator can edit it to group requirements "
            "the rule missed. See docs/OPEN_QUESTIONS.md Q17."
        ),
    )
    precedence_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequirementStatus] = mapped_column(
        pg_enum(RequirementStatus, "requirement_status"), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=True,
        comment=(
            "The curator who approved this requirement. Not in the architecture doc's field "
            "table, but a safety requirement that went live with nobody's name on it cannot "
            "be defended later."
        ),
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ruleset_version: Mapped[str] = mapped_column(String(20), nullable=False)
