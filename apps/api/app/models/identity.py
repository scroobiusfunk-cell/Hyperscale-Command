"""Project and user records.

Neither is described in docs/ARCHITECTURE.md as a record of its own, but both
are needed for the core records to have real foreign keys: a ruling that cannot
name a real person is the thing CLAUDE.md forbids. Kept deliberately thin —
SSO owns identity, this table only mirrors enough of it to reference.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cxalloy_project_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AppUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """`user` is reserved in Postgres, hence app_user."""

    __tablename__ = "app_user"
    __table_args__ = (UniqueConstraint("oidc_subject", name="uq_app_user_oidc_subject"),)

    oidc_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    roles: Mapped[list[UserRole]] = mapped_column(
        ARRAY(pg_enum(UserRole, "user_role")), nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
