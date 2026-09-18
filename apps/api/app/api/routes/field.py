"""The field app's API surface.

Three calls: download a walk, commit to it, and sync the event log back. The app
is offline between the second and the third, which is why the third is the one
that had to be idempotent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.capture.walk import DeclaredState, Walk, compile_walk, start_walk
from app.coaching import service as coaching
from app.deps import AppSettings, CurrentUser, DbSession, Storage
from app.models.enums import Criticality, RulingVerdict
from app.sync.blobs import BlobRejectedError, confirm_uploads, store_blob
from app.sync.events import EventEnvelope
from app.sync.replay import sync as apply_sync

router = APIRouter(prefix="/field", tags=["field"])


class DeclaredStateRequest(BaseModel):
    """What the tech says is true at the start of the walk."""

    open_rooms: list[str] | None = Field(
        default=None, description="Null means everything is open; an empty list means nothing is."
    )
    energized_rooms: list[str] = Field(default_factory=list)
    ladder_available: bool = False
    confined_space_permit: bool = False
    room: str | None = None
    asset_ids: list[uuid.UUID] = Field(default_factory=list)

    def to_declared(self) -> DeclaredState:
        return DeclaredState(
            open_rooms=frozenset(self.open_rooms) if self.open_rooms is not None else None,
            energized_rooms=frozenset(self.energized_rooms),
            ladder_available=self.ladder_available,
            confined_space_permit=self.confined_space_permit,
        )


class WalkStepResponse(BaseModel):
    instruction: str
    framing_rule: str
    gate_check: str


class WalkItemResponse(BaseModel):
    checklist_item_id: uuid.UUID
    statement: str
    why_it_matters: str
    criticality: Criticality
    capture_recipe_id: uuid.UUID
    recipe_slug: str
    recipe_version: str
    reference_media_slot: str | None
    disqualifiers: list[str]
    scaffold_level: str
    steps: list[WalkStepResponse]


class WalkStopResponse(BaseModel):
    asset_id: uuid.UUID
    tag: str
    room: str | None
    grid_ref: str | None
    items: list[WalkItemResponse]


class DeferredResponse(BaseModel):
    checklist_item_id: uuid.UUID
    asset_tag: str
    reason: str
    note: str


class WalkResponse(BaseModel):
    stops: list[WalkStopResponse]
    deferred: list[DeferredResponse]
    unroutable: list[DeferredResponse]
    item_count: int

    @classmethod
    def of(cls, walk: Walk) -> WalkResponse:
        return cls(
            stops=[
                WalkStopResponse(
                    asset_id=stop.asset_id,
                    tag=stop.tag,
                    room=stop.room,
                    grid_ref=stop.grid_ref,
                    items=[
                        WalkItemResponse(
                            checklist_item_id=item.checklist_item_id,
                            statement=item.statement,
                            why_it_matters=item.why_it_matters,
                            criticality=item.criticality,
                            capture_recipe_id=item.recipe_id,
                            recipe_slug=item.recipe_slug,
                            recipe_version=item.recipe_version,
                            reference_media_slot=item.reference_media_slot,
                            disqualifiers=list(item.disqualifiers),
                            scaffold_level=item.scaffold_level,
                            steps=[
                                WalkStepResponse(
                                    instruction=step.instruction,
                                    framing_rule=step.framing_rule,
                                    gate_check=step.gate_check,
                                )
                                for step in item.steps
                            ],
                        )
                        for item in stop.items
                    ],
                )
                for stop in walk.stops
            ],
            deferred=[
                DeferredResponse(
                    checklist_item_id=d.checklist_item_id,
                    asset_tag=d.asset_tag,
                    reason=d.reason.value,
                    note=d.note,
                )
                for d in walk.deferred
            ],
            unroutable=[
                DeferredResponse(
                    checklist_item_id=d.checklist_item_id,
                    asset_tag=d.asset_tag,
                    reason=d.reason.value,
                    note=d.note,
                )
                for d in walk.unroutable
            ],
            item_count=walk.item_count,
        )


class ChangedResponse(BaseModel):
    checklist_item_id: uuid.UUID
    message: str


class SyncResponse(BaseModel):
    accepted: int
    duplicates: int
    applied: int
    superseded: int
    rejected: int
    evidence_created: int
    changed_while_you_were_away: list[ChangedResponse]


def _compile(session: DbSession, project_id: uuid.UUID, body: DeclaredStateRequest) -> Walk:
    return compile_walk(
        session,
        project_id=project_id,
        declared=body.to_declared(),
        room=body.room,
        asset_ids=frozenset(body.asset_ids) if body.asset_ids else None,
    )


@router.post("/projects/{project_id}/walk", response_model=WalkResponse)
def preview_walk(
    project_id: uuid.UUID,
    body: DeclaredStateRequest,
    session: DbSession,
    user: CurrentUser,
) -> WalkResponse:
    """What the walk would be. Records nothing."""
    return WalkResponse.of(_compile(session, project_id, body))


@router.post(
    "/projects/{project_id}/walk/start",
    response_model=WalkResponse,
    status_code=status.HTTP_201_CREATED,
)
def begin_walk(
    project_id: uuid.UUID,
    body: DeclaredStateRequest,
    session: DbSession,
    user: CurrentUser,
) -> WalkResponse:
    """Commit to the walk: record the deferrals and assign the items."""
    walk = _compile(session, project_id, body)
    start_walk(session, walk, assigned_tech=user.id)
    return WalkResponse.of(walk)


class BlobResponse(BaseModel):
    storage_key: str
    byte_size: int
    content_hash: str
    first_time: bool
    evidence_confirmed: bool


@router.post("/evidence/{client_id}/blob", response_model=BlobResponse)
async def upload_evidence_blob(
    client_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    storage: Storage,
    content_hash: Annotated[str, Form(pattern=r"^[0-9a-fA-F]{64}$")],
    file: Annotated[UploadFile, File()],
) -> BlobResponse:
    """Upload one capture's bytes.

    Separate from the event log because photographs are large and site signal is
    not. Either call can arrive first and both are safe to repeat.
    """
    data = await file.read()
    try:
        stored = store_blob(
            session,
            storage,
            settings.evidence_bucket,
            client_id=client_id,
            data=data,
            content_hash=content_hash,
            mime_type=file.content_type or "application/octet-stream",
        )
    except BlobRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    return BlobResponse(
        storage_key=stored.storage_key,
        byte_size=stored.byte_size,
        content_hash=stored.content_hash,
        first_time=stored.first_time,
        evidence_confirmed=stored.evidence_confirmed,
    )


@router.post("/sync", response_model=SyncResponse)
def sync_events(
    envelope: EventEnvelope,
    session: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    storage: Storage,
) -> SyncResponse:
    """Apply a device's event log. Safe to call again with the same events."""
    result = apply_sync(session, submitted_by=user.id, envelope=envelope)
    # Bytes that arrived before their event stop being stuck here.
    confirm_uploads(session, storage, settings.evidence_bucket)
    return SyncResponse(
        accepted=result.accepted,
        duplicates=result.duplicates,
        applied=result.applied,
        superseded=result.superseded,
        rejected=result.rejected,
        evidence_created=result.evidence_created,
        changed_while_you_were_away=[
            ChangedResponse(checklist_item_id=c.checklist_item_id, message=c.message)
            for c in result.tell_the_tech
        ],
    )


class FeedbackResponse(BaseModel):
    checklist_item_id: uuid.UUID
    asset_tag: str
    room: str | None
    statement: str
    why_it_matters: str
    criticality: Criticality
    verdict: RulingVerdict
    note: str | None
    reviewer_name: str
    ruled_at: datetime
    needs_another_visit: bool
    is_correction: bool
    evidence_ids: list[uuid.UUID]


class TallyResponse(BaseModel):
    ruled: int
    passed: int
    failed: int
    recapture_requested: int
    awaiting_review: int


class AgreementResponse(BaseModel):
    item_type: str
    compared: int
    agreed: int
    unsure: int
    caught: int
    missed: int
    over_called: int
    rate: float | None


class MyWorkResponse(BaseModel):
    tally: TallyResponse
    agreement: AgreementResponse
    by_item_type: list[AgreementResponse]
    feedback: list[FeedbackResponse]


@router.get("/my-work", response_model=MyWorkResponse)
def read_my_work(
    session: DbSession,
    user: CurrentUser,
    project_id: uuid.UUID | None = None,
    limit: int = 100,
) -> MyWorkResponse:
    """What reviewers said about work this tech captured.

    The teaching loop's return path. Not the learner model: no score, no
    threshold, and nothing here changes what anyone is allowed to do.
    """
    result = coaching.my_work(session, tech_id=user.id, project_id=project_id, limit=limit)
    overall, per_type = coaching.agreement(session, tech_id=user.id, project_id=project_id)
    return MyWorkResponse(
        tally=TallyResponse(
            ruled=result.tally.ruled,
            passed=result.tally.passed,
            failed=result.tally.failed,
            recapture_requested=result.tally.recapture_requested,
            awaiting_review=result.tally.awaiting_review,
        ),
        agreement=_agreement(overall),
        by_item_type=[_agreement(a) for a in per_type],
        feedback=[
            FeedbackResponse(
                checklist_item_id=f.checklist_item_id,
                asset_tag=f.asset_tag,
                room=f.room,
                statement=f.statement,
                why_it_matters=f.why_it_matters,
                criticality=f.criticality,
                verdict=f.verdict,
                note=f.note,
                reviewer_name=f.reviewer_name,
                ruled_at=f.ruled_at,
                needs_another_visit=f.needs_another_visit,
                is_correction=f.is_correction,
                evidence_ids=list(f.evidence_ids),
            )
            for f in result.feedback
        ],
    )


def _agreement(a: coaching.Agreement) -> AgreementResponse:
    return AgreementResponse(
        item_type=a.item_type,
        compared=a.compared,
        agreed=a.agreed,
        unsure=a.unsure,
        caught=a.caught,
        missed=a.missed,
        over_called=a.over_called,
        rate=a.rate,
    )
