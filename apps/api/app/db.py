"""Database engine and session management.

Models are not defined yet. `Base` exists so Alembic's autogenerate has a
metadata target from the first migration onward.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def build_engine(settings: Settings):  # type: ignore[no-untyped-def]
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def build_session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(bind=build_engine(settings), expire_on_commit=False, future=True)


def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional scope around a series of operations."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
