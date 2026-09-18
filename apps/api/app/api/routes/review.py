"""Reviewer console endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.deps import AppSettings, CurrentUser, DbSession
from app.models import Evidence
from app.models.enums import Criticality, RulingVerdict
from app.review import service
from app.storage import S3Storage, StorageError

router = APIRouter(prefix="/review", tags=["review"])


class QueueEntryResponse(BaseModel):
    checklist_item_id: uuid.UUID
    asset_tag: str
    room: str | None
    statement: str
    criticality: Criticality
    evidence_count: int
    captured_at: str | None
    is_recapture: bool


class EvidenceResponse(BaseModel):
    evidence_id: uuid.UUID
    step_index: int
    captured_at: str
    mime_type: str
    gate_results: list[dict[str, Any]]
    is_retake: bool


class RulingResponse(BaseModel):
    id: uuid.UUID
    verdict: RulingVerdict
    note: str | None
    reviewer_id: uuid.UUID
    created_at: str
    supersedes: uuid.UUID | None


class ItemDetailResponse(BaseModel):
    checklist_item_id: uuid.UUID
    asset_tag: str
    asset_cxalloy_id: str | None
    room: str | None
    equipment_class: str
    statement: str
    why_it_matters: str
    criticality: Criticality
    pass_criteria: dict[str, Any]
    source_clause: str
    source_page: int
    ruleset_version: str
    state: str
    evidence: list[EvidenceResponse]
    history: list[RulingResponse]


class RuleRequest(BaseModel):
    verdict: RulingVerdict
    note: str | None = Field(default=None, max_length=2000)


class ReviewerStatsResponse(BaseModel):
    reviewer_id: uuid.UUID
    display_name: str
    rulings: int
    passes: int
    fails: int
    recaptures: int
    notes_on_passes: int
    labeling_rate: float


class DashboardResponse(BaseModel):
    awaiting_review: int
    safety_awaiting_review: int
    undelivered: int
    undelivered_failures: int
    unresolved_assets: int
    reviewers: list[ReviewerStatsResponse]


def _conflict(exc: service.ReviewError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/projects/{project_id}/queue", response_model=list[QueueEntryResponse])
def read_queue(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> list[QueueEntryResponse]:
    return [
        QueueEntryResponse(
            checklist_item_id=e.checklist_item_id,
            asset_tag=e.asset_tag,
            room=e.room,
            statement=e.statement,
            criticality=e.criticality,
            evidence_count=e.evidence_count,
            captured_at=e.captured_at.isoformat() if e.captured_at else None,
            is_recapture=e.is_recapture,
        )
        for e in service.queue(session, project_id=project_id)
    ]


@router.get("/items/{checklist_item_id}", response_model=ItemDetailResponse)
def read_item(
    checklist_item_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> ItemDetailResponse:
    try:
        detail = service.item_detail(session, checklist_item_id)
    except service.ReviewError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ItemDetailResponse(
        checklist_item_id=detail.checklist_item_id,
        asset_tag=detail.asset_tag,
        asset_cxalloy_id=detail.asset_cxalloy_id,
        room=detail.room,
        equipment_class=detail.equipment_class,
        statement=detail.statement,
        why_it_matters=detail.why_it_matters,
        criticality=detail.criticality,
        pass_criteria=detail.pass_criteria,
        source_clause=detail.source_clause,
        source_page=detail.source_page,
        ruleset_version=detail.ruleset_version,
        state=detail.state.value,
        evidence=[
            EvidenceResponse(
                evidence_id=e.evidence_id,
                step_index=e.step_index,
                captured_at=e.captured_at.isoformat(),
                mime_type=e.mime_type,
                gate_results=[dict(g) for g in e.gate_results],
                is_retake=e.is_retake,
            )
            for e in detail.evidence
        ],
        history=[
            RulingResponse(
                id=r.id,
                verdict=r.verdict,
                note=r.note,
                reviewer_id=r.reviewer_id,
                created_at=r.created_at.isoformat(),
                supersedes=r.supersedes,
            )
            for r in detail.history
        ],
    )


@router.post("/items/{checklist_item_id}/rule", response_model=RulingResponse)
def rule_item(
    checklist_item_id: uuid.UUID,
    body: RuleRequest,
    session: DbSession,
    user: CurrentUser,
) -> RulingResponse:
    """The ruling and its note, as one action."""
    try:
        ruling = service.rule(
            session,
            checklist_item_id,
            reviewer_id=user.id,
            verdict=body.verdict,
            note=body.note,
        )
    except service.ReviewError as exc:
        raise _conflict(exc) from exc

    return RulingResponse(
        id=ruling.id,
        verdict=ruling.verdict,
        note=ruling.note,
        reviewer_id=ruling.reviewer_id,
        created_at=ruling.created_at.isoformat(),
        supersedes=ruling.supersedes,
    )


@router.get("/evidence/{evidence_id}/image")
def read_evidence_image(
    evidence_id: uuid.UUID, session: DbSession, user: CurrentUser, settings: AppSettings
) -> Response:
    """Stream one piece of evidence.

    Served through the API rather than by a link into object storage, so that
    looking at a photograph needs the same identity as ruling on it.
    """
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such evidence.")

    try:
        body = S3Storage.from_settings(settings).get(settings.evidence_bucket, evidence.storage_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That photo has not been uploaded yet.",
        ) from exc

    return Response(content=body, media_type=evidence.mime_type)


@router.get("/projects/{project_id}/dashboard", response_model=DashboardResponse)
def read_dashboard(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> DashboardResponse:
    result = service.dashboard(session, project_id=project_id)
    return DashboardResponse(
        awaiting_review=result.awaiting_review,
        safety_awaiting_review=result.safety_awaiting_review,
        undelivered=result.undelivered,
        undelivered_failures=result.undelivered_failures,
        unresolved_assets=result.unresolved_assets,
        reviewers=[
            ReviewerStatsResponse(
                reviewer_id=s.reviewer_id,
                display_name=s.display_name,
                rulings=s.rulings,
                passes=s.passes,
                fails=s.fails,
                recaptures=s.recaptures,
                notes_on_passes=s.notes_on_passes,
                labeling_rate=s.labeling_rate,
            )
            for s in result.reviewers
        ],
    )
