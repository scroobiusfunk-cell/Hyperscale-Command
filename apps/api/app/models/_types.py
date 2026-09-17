"""Helpers for declaring columns consistently."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """A native Postgres enum storing the enum's *values*, not its member names.

    Without values_callable SQLAlchemy stores member names (SAFETY), which would
    not match packages/schemas or anything the API returns.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
