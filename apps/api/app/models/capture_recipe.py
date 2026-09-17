"""Capture recipes.

Recipes are versioned and shared across projects, so they carry no project_id;
the project-specific part is which recipe a requirement points to. Steps,
disqualifiers and the gate checks are JSONB rather than child tables: nothing
queries inside them, and they are always read whole as part of a walk payload.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import VerificationMethod


class CaptureRecipe(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "capture_recipe"
    __table_args__ = (UniqueConstraint("slug", "version", name="uq_capture_recipe_slug_version"),)

    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    verification_method: Mapped[VerificationMethod] = mapped_column(
        pg_enum(VerificationMethod, "verification_method"), nullable=False
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    disqualifiers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    reference_media_slot: Mapped[str | None] = mapped_column(String(255), nullable=True)
