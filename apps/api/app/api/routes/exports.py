"""Results export endpoints.

CxAlloy's API is read only, so there is no "push to CxAlloy" here. There is
build a package, download it, and confirm a person imported it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.cxalloy.export import (
    ExportError,
    build_export,
    confirm_delivery,
    delivery_status,
)
from app.deps import AppSettings, CurrentUser, DbSession
from app.models import ResultsExport
from app.storage import S3Storage

router = APIRouter(tags=["exports"])


class ExportResponse(BaseModel):
    id: uuid.UUID
    status: str
    item_count: int
    failure_count: int
    storage_key: str | None
    content_hash: str | None
    confirmed_by: uuid.UUID | None

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
    user: CurrentUser,
    settings: AppSettings,
) -> ExportResponse:
    """Render every undelivered ruling into one package."""
    try:
        export = build_export(
            session,
            S3Storage.from_settings(settings),
            project_id=project_id,
            bucket=settings.exports_bucket,
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
    result = delivery_status(session, project_id)
    return DeliveryStatusResponse(
        pending_export=result.pending_export,
        exported_not_confirmed=result.exported_not_confirmed,
        undelivered=result.undelivered,
        undelivered_failures=result.undelivered_failures,
    )
