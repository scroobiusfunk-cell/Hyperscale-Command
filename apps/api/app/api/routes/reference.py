"""Worked examples: uploading them, listing them, and serving the bytes.

Teaching material is not evidence, and the two are governed differently. An
evidence photograph shows one asset on one day and is only the business of the
people judging it. A reference image is a lesson, put there deliberately to be
looked at, so any signed-in person on the project may open one. Adding them is
narrower: only a reviewer, curator or admin.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from app.coaching.reference import (
    ReferenceRejectedError,
    add_reference,
    promote_evidence,
    references_for,
)
from app.deps import AppSettings, CurrentUser, DbSession, Storage
from app.models import ReferenceImage
from app.models.enums import ReferenceKind
from app.storage import StorageError

router = APIRouter(prefix="/reference", tags=["reference"])


class ReferenceResponse(BaseModel):
    reference_image_id: uuid.UUID
    item_type: str
    kind: ReferenceKind
    caption: str
    mime_type: str
    display_order: int
    sourced_from_evidence_id: uuid.UUID | None


def _view(row: ReferenceImage) -> ReferenceResponse:
    return ReferenceResponse(
        reference_image_id=row.id,
        item_type=row.item_type,
        kind=row.kind,
        caption=row.caption,
        mime_type=row.mime_type,
        display_order=row.display_order,
        sourced_from_evidence_id=row.sourced_from_evidence_id,
    )


@router.post(
    "/projects/{project_id}/images",
    response_model=ReferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_reference(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    storage: Storage,
    item_type: Annotated[str, Form(min_length=1, max_length=100)],
    kind: Annotated[ReferenceKind, Form()],
    caption: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    display_order: Annotated[int, Form()] = 0,
) -> ReferenceResponse:
    """Add a worked example for one kind of check."""
    try:
        row = add_reference(
            session,
            storage,
            settings.reference_bucket,
            project_id=project_id,
            item_type=item_type,
            kind=kind,
            caption=caption,
            data=await file.read(),
            mime_type=file.content_type or "image/jpeg",
            added_by=user.id,
            display_order=display_order,
        )
    except ReferenceRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return _view(row)


@router.post(
    "/from-evidence/{evidence_id}",
    response_model=ReferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote(
    evidence_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    storage: Storage,
    kind: Annotated[ReferenceKind, Form()],
    caption: Annotated[str, Form()],
    display_order: Annotated[int, Form()] = 0,
) -> ReferenceResponse:
    """Promote a real capture into teaching material, captioned."""
    try:
        row = promote_evidence(
            session,
            storage,
            settings.evidence_bucket,
            settings.reference_bucket,
            evidence_id=evidence_id,
            kind=kind,
            caption=caption,
            added_by=user.id,
            display_order=display_order,
        )
    except ReferenceRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return _view(row)


@router.get("/projects/{project_id}/images", response_model=list[ReferenceResponse])
def list_references(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    item_type: str | None = None,
) -> list[ReferenceResponse]:
    """Every active example for a project, or for one kind of check."""
    query = select(ReferenceImage).where(
        ReferenceImage.project_id == project_id, ReferenceImage.is_active.is_(True)
    )
    if item_type is not None:
        query = query.where(ReferenceImage.item_type == item_type)
    rows = (
        session.execute(
            query.order_by(
                ReferenceImage.item_type, ReferenceImage.display_order, ReferenceImage.id
            )
        )
        .scalars()
        .all()
    )
    return [_view(r) for r in rows]


@router.get("/images/{reference_image_id}")
def read_reference_image(
    reference_image_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    storage: Storage,
) -> Response:
    """Serve one example. Teaching material, so any signed-in person may look."""
    row = session.get(ReferenceImage, reference_image_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such example.")
    try:
        body = storage.get(settings.reference_bucket, row.storage_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That example is not stored."
        ) from exc
    return Response(content=body, media_type=row.mime_type)


@router.post("/images/{reference_image_id}/retire", response_model=ReferenceResponse)
def retire_reference(
    reference_image_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> ReferenceResponse:
    """Take an example out of circulation without deleting what was taught."""
    row = session.get(ReferenceImage, reference_image_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such example.")
    row.is_active = False
    session.flush()
    return _view(row)


__all__ = ["references_for", "router"]
