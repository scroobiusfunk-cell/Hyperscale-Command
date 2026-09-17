"""Curation endpoints.

The side-by-side curation UI in the architecture doc reads from these: the
requirement, its source clause and page, and the decision the curator makes.
Business rules live in `app.requirements_compiler.rule_set`; this module is
transport.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Requirement, RuleSet
from app.models.enums import Criticality, RequirementStatus, VerificationMethod
from app.requirements_compiler import rule_set as service

router = APIRouter(tags=["curation"])


class CreateRuleSetRequest(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    supersedes_id: uuid.UUID | None = None
    notes: str | None = None


class RuleSetResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: str
    status: str
    supersedes_id: uuid.UUID | None
    published_by: uuid.UUID | None

    @classmethod
    def of(cls, rule_set: RuleSet) -> RuleSetResponse:
        return cls(
            id=rule_set.id,
            project_id=rule_set.project_id,
            version=rule_set.version,
            status=rule_set.status.value,
            supersedes_id=rule_set.supersedes_id,
            published_by=rule_set.published_by,
        )


class RequirementResponse(BaseModel):
    """Everything the curation screen shows side by side with the page image."""

    id: uuid.UUID
    ruleset_version: str
    statement: str
    why_it_matters: str
    verification_method: VerificationMethod
    criticality: Criticality
    status: RequirementStatus
    pass_criteria: dict[str, Any]
    applies_to_equipment_class: list[str]
    applies_to_system: str | None
    applies_to_location_type: str | None
    source_doc_id: uuid.UUID
    source_clause: str
    source_page: int
    precedence_rank: int
    approved_by: uuid.UUID | None

    @classmethod
    def of(cls, requirement: Requirement) -> RequirementResponse:
        return cls(
            id=requirement.id,
            ruleset_version=requirement.ruleset_version,
            statement=requirement.statement,
            why_it_matters=requirement.why_it_matters,
            verification_method=requirement.verification_method,
            criticality=requirement.criticality,
            status=requirement.status,
            pass_criteria=requirement.pass_criteria,
            applies_to_equipment_class=list(requirement.applies_to_equipment_class),
            applies_to_system=requirement.applies_to_system,
            applies_to_location_type=requirement.applies_to_location_type,
            source_doc_id=requirement.source_doc_id,
            source_clause=requirement.source_clause,
            source_page=requirement.source_page,
            precedence_rank=requirement.precedence_rank,
            approved_by=requirement.approved_by,
        )


class PublishResponse(BaseModel):
    rule_set_id: uuid.UUID
    version: str
    approved: int
    left_behind: int


class FieldChangeResponse(BaseModel):
    field: str
    before: Any
    after: Any


class RequirementChangeResponse(BaseModel):
    requirement_id: uuid.UUID
    changes: list[FieldChangeResponse]


class DiffResponse(BaseModel):
    base_version: str
    head_version: str
    added: list[uuid.UUID]
    removed: list[uuid.UUID]
    changed: list[RequirementChangeResponse]
    unchanged: int


def _conflict(exc: service.CurationError) -> HTTPException:
    detail: Any = (
        {"reasons": exc.reasons} if isinstance(exc, service.PublishRefusedError) else str(exc)
    )
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _load_rule_set(session: DbSession, rule_set_id: uuid.UUID) -> RuleSet:
    rule_set = session.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such rule set.")
    return rule_set


@router.post(
    "/projects/{project_id}/rule-sets",
    response_model=RuleSetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rule_set(
    project_id: uuid.UUID,
    body: CreateRuleSetRequest,
    session: DbSession,
    user: CurrentUser,
) -> RuleSetResponse:
    try:
        rule_set = service.create_draft(
            session,
            project_id,
            body.version,
            supersedes_id=body.supersedes_id,
            notes=body.notes,
        )
    except service.CurationError as exc:
        raise _conflict(exc) from exc
    return RuleSetResponse.of(rule_set)


@router.get("/rule-sets/{rule_set_id}", response_model=RuleSetResponse)
def read_rule_set(rule_set_id: uuid.UUID, session: DbSession, user: CurrentUser) -> RuleSetResponse:
    return RuleSetResponse.of(_load_rule_set(session, rule_set_id))


@router.get("/rule-sets/{rule_set_id}/requirements", response_model=list[RequirementResponse])
def list_requirements(
    rule_set_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    requirement_status: Annotated[RequirementStatus | None, Query(alias="status")] = None,
) -> list[RequirementResponse]:
    _load_rule_set(session, rule_set_id)
    stmt = select(Requirement).where(Requirement.rule_set_id == rule_set_id)
    if requirement_status is not None:
        stmt = stmt.where(Requirement.status == requirement_status)
    # Safety first, then by source order: the curator's attention is the scarce
    # resource and the safety items are the ones that cannot be skipped.
    requirements = sorted(
        session.execute(stmt).scalars().all(),
        key=lambda r: (r.criticality is not Criticality.SAFETY, r.source_page, r.source_clause),
    )
    return [RequirementResponse.of(r) for r in requirements]


@router.post(
    "/rule-sets/{rule_set_id}/requirements/{requirement_id}/approve",
    response_model=RequirementResponse,
)
def approve_requirement(
    rule_set_id: uuid.UUID,
    requirement_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> RequirementResponse:
    rule_set = _load_rule_set(session, rule_set_id)
    try:
        requirement = service.approve_requirement(
            session, requirement_id, rule_set.version, approved_by=user.id
        )
    except service.CurationError as exc:
        raise _conflict(exc) from exc
    return RequirementResponse.of(requirement)


@router.post(
    "/rule-sets/{rule_set_id}/requirements/{requirement_id}/reject",
    response_model=RequirementResponse,
)
def reject_requirement(
    rule_set_id: uuid.UUID,
    requirement_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> RequirementResponse:
    rule_set = _load_rule_set(session, rule_set_id)
    try:
        requirement = service.reject_requirement(
            session, requirement_id, rule_set.version, rejected_by=user.id
        )
    except service.CurationError as exc:
        raise _conflict(exc) from exc
    return RequirementResponse.of(requirement)


@router.post("/rule-sets/{rule_set_id}/publish", response_model=PublishResponse)
def publish_rule_set(
    rule_set_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> PublishResponse:
    _load_rule_set(session, rule_set_id)
    try:
        summary = service.publish(session, rule_set_id, published_by=user.id)
    except service.CurationError as exc:
        raise _conflict(exc) from exc
    return PublishResponse(
        rule_set_id=summary.rule_set_id,
        version=summary.version,
        approved=summary.approved,
        left_behind=summary.left_behind,
    )


@router.get("/rule-sets/{base_id}/diff/{head_id}", response_model=DiffResponse)
def diff_rule_sets(
    base_id: uuid.UUID, head_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> DiffResponse:
    _load_rule_set(session, base_id)
    _load_rule_set(session, head_id)
    result = service.diff(session, base_id, head_id)
    return DiffResponse(
        base_version=result.base_version,
        head_version=result.head_version,
        added=list(result.added),
        removed=list(result.removed),
        changed=[
            RequirementChangeResponse(
                requirement_id=c.requirement_id,
                changes=[
                    FieldChangeResponse(field=f.field, before=f.before, after=f.after)
                    for f in c.changes
                ],
            )
            for c in result.changed
        ],
        unchanged=result.unchanged,
    )
