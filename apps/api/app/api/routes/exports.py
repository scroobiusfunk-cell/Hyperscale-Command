"""Results export endpoints.

CxAlloy's API is read only, so there is no "push to CxAlloy" here. There is
build a package, download it, and confirm a person imported it.

All three need the same permission and it is checked in one place. A package is
the whole project's rulings in one file — see `authz.may_handle_exports`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.authz import may_handle_exports
from app.cxalloy.export import (
    ExportError,
    build_export,
    confirm_delivery,
    delivery_status,
)
from app.deps import AppSettings, CurrentUser, DbSession, Storage
from app.models import AppUser, ResultsExport
from app.storage import StorageError

router = APIRouter(tags=["exports"])

#: One answer for "not yours" and "no such package", so neither can be used to
#: learn which project ids exist.
_NOT_AVAILABLE = "No such package, or it is not yours to handle."


def _require_export_access(user: AppUser) -> None:
    if not may_handle_exports(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_AVAILABLE)


class ExportResponse(BaseModel):
    id: uuid.UUID
    status: str
    item_count: int
    failure_count: int
    storage_key: str | None
    content_hash: str | None
    confirmed_by: uuid.UUID | None
    #: The console shows when a package was built and when somebody said it was
    #: entered. "Exported, not confirmed" is only actionable with a date on it.
    created_at: datetime
    confirmed_at: datetime | None
    #: Whether there are bytes to download. An empty package is a real outcome —
    #: it means nothing was waiting — and offering a download for it is a lie.
    has_file: bool

    @classmethod
    def of(cls, export: ResultsExport) -> ExportResponse:
        return cls(
            id=export.id,
            status=export.status.value,
            item_count=export.item_count,
            failure_count=export.failure_count,
            storage_key=export.storage_key,
            content_hash=export.content_hash,
            confirmed_by=export.confirmed_by,
            created_at=export.created_at,
            confirmed_at=export.confirmed_at,
            has_file=bool(export.storage_key) and export.item_count > 0,
        )


class DeliveryStatusResponse(BaseModel):
    pending_export: int
    exported_not_confirmed: int
    undelivered: int
    undelivered_failures: int


@router.post(
    "/projects/{project_id}/exports",
    response_model=ExportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_export(
    project_id: uuid.UUID,
    session: DbSession,
    storage: Storage,
    user: CurrentUser,
    settings: AppSettings,
) -> ExportResponse:
    """Render every undelivered ruling into one package.

    Storage arrives as a dependency rather than being built here, so that the
    route that writes the package and the route that serves it are looking at
    the same one — in a test that is the difference between a round trip and
    two unrelated halves.
    """
    _require_export_access(user)
    try:
        export = build_export(
            session,
            storage,
            project_id=project_id,
            bucket=settings.exports_bucket,
            evidence_bucket=settings.evidence_bucket,
        )
    except ExportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return ExportResponse.of(export)


@router.get("/projects/{project_id}/exports", response_model=list[ExportResponse])
def list_exports(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> list[ExportResponse]:
    _require_export_access(user)
    exports = (
        session.execute(
            select(ResultsExport)
            .where(ResultsExport.project_id == project_id)
            .order_by(ResultsExport.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [ExportResponse.of(e) for e in exports]


@router.post("/exports/{export_id}/confirm-delivery", response_model=ExportResponse)
def confirm(export_id: uuid.UUID, session: DbSession, user: CurrentUser) -> ExportResponse:
    """A person says the import into CxAlloy is done.

    This is the only thing that clears the undelivered count. The platform
    cannot confirm on their behalf; its access to CxAlloy is read only.
    """
    _require_export_access(user)
    try:
        export = confirm_delivery(session, export_id, confirmed_by=user.id)
    except ExportError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ExportResponse.of(export)


@router.get("/projects/{project_id}/delivery-status", response_model=DeliveryStatusResponse)
def read_delivery_status(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> DeliveryStatusResponse:
    """Tracked from day one, alongside reconciliation queue size."""
    _require_export_access(user)
    result = delivery_status(session, project_id)
    return DeliveryStatusResponse(
        pending_export=result.pending_export,
        exported_not_confirmed=result.exported_not_confirmed,
        undelivered=result.undelivered,
        undelivered_failures=result.undelivered_failures,
    )


@router.get("/exports/{export_id}/file")
def download_export(
    export_id: uuid.UUID,
    session: DbSession,
    storage: Storage,
    settings: AppSettings,
    user: CurrentUser,
) -> Response:
    """The package itself.

    Without this the console could build a package and ask somebody to work
    through it in CxAlloy while giving them no way to open it, which is what it
    did. The bytes are served through the API rather than by a signed storage
    URL: the object store is not reachable from a reviewer's laptop in any
    deployment we have, and a link that outlives the session is a copy of the
    whole project's rulings sitting in somebody's history.
    """
    _require_export_access(user)

    export = session.get(ResultsExport, export_id)
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_AVAILABLE)
    if not export.storage_key or export.item_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "That package is empty — there was nothing waiting when it was built. "
                "Nothing to enter."
            ),
        )

    try:
        data = storage.get(settings.exports_bucket, export.storage_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That package was recorded but its file is not in storage.",
        ) from exc

    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="understudy-export-{export_id}.zip"'
        },
    )
