"""FastAPI dependencies.

The identity dependency is deliberately blunt. Phase 1 cannot ship on fake
logins — a reviewer's ruling on a safety item has to carry a real person's name
— so when SSO is not configured the API says so with a 501 rather than
inventing a user. The development identity header is the only alternative, and
`Settings` already refuses to start with it enabled outside development.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AppUser


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    x_dev_user_id: Annotated[uuid.UUID | None, Header()] = None,
) -> AppUser:
    if not settings.auth_dev_identity_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Company SSO is not configured for this environment. See docs/OPEN_QUESTIONS.md Q7."
            ),
        )

    if x_dev_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Development identity is enabled but no X-Dev-User-Id header was sent.",
        )

    user = session.get(AppUser, x_dev_user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No such active user.")
    return user


AppSettings = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[AppUser, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_session)]
