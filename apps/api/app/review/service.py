"""Reviewing an item.

"Design the reviewer console so the ruling and a one-line note are the same
action, and report labeling rate per reviewer alongside their throughput."

That is one sentence with two separate demands in it, and they pull against each
other. Make the note mandatory everywhere and the labeling rate is 100% by
construction — a number that cannot tell you anything. Make it optional and
reviewers under time pressure stop writing them, which is the failure the
sentence is warning about.

The split here: a note is **required** for a fail and for a recapture, because
"this is wrong" without saying what is wrong is not a ruling anybody can act on.
It is **optional on a pass**, and the labeling rate measures how many passes
carry one. So the rate stays meaningful, and it measures the thing actually at
risk: a reviewer clearing obvious items quickly and silently.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import (
    AppUser,
    Asset,
    ChecklistItem,
    Evidence,
    LabeledExample,
    Requirement,
    Ruling,
)
from app.models.enums import (
    ChecklistItemState,
    Criticality,
    CxAlloyDeliveryState,
    UserRole,
    Verdict,
    VerdictReason,
)
from app.requirements_compiler.grouping import item_type_of

log = get_logger(__name__)

#: States an item can be reviewed from. Anything else has either not been walked
#: yet or has already been decided.
REVIEWABLE_STATES = frozenset({ChecklistItemState.EVIDENCE_CAPTURED, ChecklistItemState.ROUTED})

#: A note shorter than this is not a note. "ok" tells the next person nothing and
#: tells the flywheel less.
MEANINGFUL_NOTE_CHARS = 8

RULING_STATE = {
    Verdict.PASS: ChecklistItemState.REVIEWER_PASSED,
    Verdict.FAIL: ChecklistItemState.REVIEWER_FAILED,
    # Only a definite judgement resolves an item. Anything else is a statement
    # about the photograph rather than the installation, so the item goes back
    # to the tech: a recapture because the shot is unusable, `not_visible`
    # because the thing could not be seen at all.
    Verdict.INDETERMINATE: ChecklistItemState.OPEN,
    Verdict.NOT_VISIBLE: ChecklistItemState.OPEN,
}

#: The reason a reviewer is allowed to give. A reviewer is not a grader and is
#: not the learner, so the other two reasons are not theirs to record.
REVIEWER_REASON = VerdictReason.RECAPTURE_REQUESTED


class ReviewError(RuntimeError):
    """A ruling that must not be recorded."""


@dataclass(frozen=True)
class QueueEntry:
    checklist_item_id: uuid.UUID
    asset_tag: str
    room: str | None
    statement: str
    criticality: Criticality
    evidence_count: int
    captured_at: datetime | None
    is_recapture: bool


@dataclass(frozen=True)
class EvidenceView:
    evidence_id: uuid.UUID
    step_index: int
    captured_at: datetime
    mime_type: str
    gate_results: list[dict[str, object]]
    is_retake: bool


@dataclass(frozen=True)
class ItemDetail:
    checklist_item_id: uuid.UUID
    asset_tag: str
    asset_cxalloy_id: str | None
    room: str | None
    equipment_class: str
    statement: str
    why_it_matters: str
    criticality: Criticality
    pass_criteria: dict[str, object]
    source_clause: str
    source_page: int
    ruleset_version: str
    state: ChecklistItemState
    evidence: list[EvidenceView]
    history: list[Ruling]


@dataclass(frozen=True)
class ReviewerStats:
    reviewer_id: uuid.UUID
    display_name: str
    rulings: int
    passes: int
    fails: int
    recaptures: int
    notes_on_passes: int
    labeling_rate: float
    """Share of passes carrying a note worth reading. The number at risk."""


@dataclass(frozen=True)
class Dashboard:
    awaiting_review: int
    safety_awaiting_review: int
    undelivered: int
    undelivered_failures: int
    unresolved_assets: int
    reviewers: list[ReviewerStats]


def queue(session: Session, *, project_id: uuid.UUID, limit: int = 200) -> list[QueueEntry]:
    """What is waiting, safety first.

    A reviewer's attention is the scarce resource the whole product is built
    around, so the ordering is not negotiable: safety items cannot wait behind a
    backlog of nameplate photos.
    """
    rows = list(
        session.execute(
            select(ChecklistItem, Asset, Requirement)
            .join(Asset, Asset.id == ChecklistItem.asset_id)
            .join(
                Requirement,
                (Requirement.id == ChecklistItem.requirement_id)
                & (Requirement.ruleset_version == ChecklistItem.ruleset_version),
            )
            .where(
                Asset.project_id == project_id,
                ChecklistItem.state.in_(REVIEWABLE_STATES),
            )
        ).all()
    )

    counts: dict[uuid.UUID, int] = {}
    latest: dict[uuid.UUID, datetime] = {}
    for evidence in (
        session.execute(
            select(Evidence).where(
                Evidence.checklist_item_id.in_({r[0].id for r in rows} or {uuid.uuid4()})
            )
        )
        .scalars()
        .all()
    ):
        counts[evidence.checklist_item_id] = counts.get(evidence.checklist_item_id, 0) + 1
        seen = latest.get(evidence.checklist_item_id)
        if seen is None or evidence.received_at > seen:
            latest[evidence.checklist_item_id] = evidence.received_at

    previously_ruled = {
        ruling.checklist_item_id
        for ruling in session.execute(
            select(Ruling).where(
                Ruling.checklist_item_id.in_({r[0].id for r in rows} or {uuid.uuid4()})
            )
        )
        .scalars()
        .all()
    }

    entries = [
        QueueEntry(
            checklist_item_id=item.id,
            asset_tag=asset.tag,
            room=asset.location_room,
            statement=requirement.statement,
            criticality=requirement.criticality,
            evidence_count=counts.get(item.id, 0),
            captured_at=latest.get(item.id),
            is_recapture=item.id in previously_ruled,
        )
        for item, asset, requirement in rows
    ]

    entries.sort(
        key=lambda e: (
            0 if e.criticality is Criticality.SAFETY else 1,
            e.captured_at or datetime.max.replace(tzinfo=UTC),
        )
    )
    return entries[:limit]


def item_detail(session: Session, checklist_item_id: uuid.UUID) -> ItemDetail:
    item = session.get(ChecklistItem, checklist_item_id)
    if item is None:
        raise ReviewError(f"No checklist item {checklist_item_id}.")

    asset = session.get(Asset, item.asset_id)
    requirement = session.get(Requirement, (item.requirement_id, item.ruleset_version))
    if asset is None or requirement is None:
        raise ReviewError("That checklist item is missing its asset or requirement.")

    evidence = list(
        session.execute(
            select(Evidence)
            .where(Evidence.checklist_item_id == item.id)
            .order_by(Evidence.step_index, Evidence.received_at)
        )
        .scalars()
        .all()
    )
    history = list(
        session.execute(
            select(Ruling).where(Ruling.checklist_item_id == item.id).order_by(Ruling.created_at)
        )
        .scalars()
        .all()
    )

    return ItemDetail(
        checklist_item_id=item.id,
        asset_tag=asset.tag,
        asset_cxalloy_id=asset.cxalloy_id,
        room=asset.location_room,
        equipment_class=asset.equipment_class,
        statement=requirement.statement,
        why_it_matters=requirement.why_it_matters,
        criticality=requirement.criticality,
        pass_criteria=dict(requirement.pass_criteria or {}),
        source_clause=requirement.source_clause,
        source_page=requirement.source_page,
        ruleset_version=item.ruleset_version,
        state=item.state,
        evidence=[
            EvidenceView(
                evidence_id=e.id,
                step_index=e.step_index,
                captured_at=e.captured_at,
                mime_type=e.mime_type,
                gate_results=list(e.gate_results or []),
                is_retake=e.retake_of is not None,
            )
            for e in evidence
        ],
        history=history,
    )


def _require_reviewer(session: Session, reviewer_id: uuid.UUID) -> AppUser:
    user = session.get(AppUser, reviewer_id)
    if user is None or not user.is_active:
        raise ReviewError("No such active user.")
    if not ({UserRole.REVIEWER, UserRole.ADMIN} & set(user.roles)):
        raise ReviewError(f"{user.display_name} is not a reviewer.")
    return user


def rule(
    session: Session,
    checklist_item_id: uuid.UUID,
    *,
    reviewer_id: uuid.UUID,
    verdict: Verdict,
    note: str | None,
    verdict_reason: VerdictReason | None = None,
    item_type: str | None = None,
) -> Ruling:
    """Record a ruling and its note as one act.

    Creates the Ruling, moves the item, and, for a pass or a fail, writes the
    LabeledExample the flywheel runs on. An indeterminate ruling produces no
    labelled example: it is a judgment about the photograph, not about the
    installation.

    `verdict_reason` is required when the verdict is `indeterminate` and refused
    otherwise, the same pairing the database enforces. A reviewer's only reason
    is `recapture_requested`; `insufficient_evidence` belongs to a grader and
    `unsure` to the learner, and a reviewer recording either would put somebody
    else's answer under their own name.
    """
    reviewer = _require_reviewer(session, reviewer_id)
    item = session.get(ChecklistItem, checklist_item_id)
    if item is None:
        raise ReviewError(f"No checklist item {checklist_item_id}.")

    requirement = session.get(Requirement, (item.requirement_id, item.ruleset_version))
    if requirement is None:
        raise ReviewError("That checklist item is missing its requirement.")

    if verdict is Verdict.INDETERMINATE:
        if verdict_reason is None:
            verdict_reason = REVIEWER_REASON
        elif verdict_reason is not REVIEWER_REASON:
            whose = (
                "a grader"
                if verdict_reason is VerdictReason.INSUFFICIENT_EVIDENCE
                else "the learner"
            )
            raise ReviewError(
                f"A reviewer cannot record {verdict_reason.value}. That is {whose}'s "
                "answer, not theirs."
            )
    elif verdict_reason is not None:
        raise ReviewError(
            f"A {verdict.value} ruling cannot also carry a reason for being indeterminate."
        )

    cleaned = (note or "").strip()
    if verdict is not Verdict.PASS and len(cleaned) < MEANINGFUL_NOTE_CHARS:
        raise ReviewError(
            "Say what is wrong. A fail or a recapture without a note is not something "
            "the tech or the next reviewer can act on."
        )

    if item.state not in REVIEWABLE_STATES and item.state not in (
        ChecklistItemState.REVIEWER_PASSED,
        ChecklistItemState.REVIEWER_FAILED,
    ):
        raise ReviewError(f"This item is {item.state.value} and is not waiting for a ruling.")

    previous = (
        session.execute(
            select(Ruling)
            .where(Ruling.checklist_item_id == item.id)
            .order_by(Ruling.created_at.desc())
        )
        .scalars()
        .first()
    )

    # A correction is a new ruling pointing at the one it replaces. The old one
    # is never edited — the database refuses to let it be.
    correcting = item.state in (
        ChecklistItemState.REVIEWER_PASSED,
        ChecklistItemState.REVIEWER_FAILED,
    )

    ruling = Ruling(
        checklist_item_id=item.id,
        verdict=verdict,
        verdict_reason=verdict_reason,
        note=cleaned or None,
        reviewer_id=reviewer.id,
        supersedes=previous.id if correcting and previous is not None else None,
    )
    session.add(ruling)
    session.flush()

    now = datetime.now(UTC)
    item.state = RULING_STATE[verdict]
    item.reviewer = reviewer.id

    if verdict is not Verdict.PASS and verdict is not Verdict.FAIL:
        item.resolved_at = None
        item.resolved_by = None
    else:
        item.resolved_at = now
        item.resolved_by = reviewer.id
        item.cxalloy_delivery_state = CxAlloyDeliveryState.PENDING_EXPORT

        evidence_ids = [
            {"evidence_id": str(e.id)}
            for e in session.execute(select(Evidence).where(Evidence.checklist_item_id == item.id))
            .scalars()
            .all()
        ]
        session.add(
            LabeledExample(
                ruling_id=ruling.id,
                checklist_item_id=item.id,
                requirement_id=item.requirement_id,
                evidence_ids=evidence_ids,
                item_type=item_type or item_type_of(requirement),
                grader_result=None,
                human_verdict=verdict,
                human_note=cleaned or None,
                reviewer_id=reviewer.id,
                labeled_at=now,
            )
        )

    session.flush()
    log.info(
        "review.ruled",
        checklist_item_id=str(item.id),
        verdict=verdict.value,
        criticality=requirement.criticality.value,
        has_note=bool(cleaned),
        correcting=correcting,
        reviewer_id=str(reviewer.id),
    )
    return ruling


def dashboard(session: Session, *, project_id: uuid.UUID, window_days: int = 30) -> Dashboard:
    """The numbers the architecture doc says to track from day one."""
    from app.cxalloy.export import delivery_status
    from app.models import ReconciliationQueueItem
    from app.models.enums import ReconciliationStatus
    from app.models.reconciliation import ReconciliationQueueStatus

    waiting = queue(session, project_id=project_id, limit=100_000)
    delivery = delivery_status(session, project_id)

    unresolved = len(
        session.execute(
            select(Asset.id).where(
                Asset.project_id == project_id,
                Asset.reconciliation_status == ReconciliationStatus.UNRESOLVED,
            )
        )
        .scalars()
        .all()
    ) + len(
        session.execute(
            select(ReconciliationQueueItem.id).where(
                ReconciliationQueueItem.project_id == project_id,
                ReconciliationQueueItem.status == ReconciliationQueueStatus.OPEN,
            )
        )
        .scalars()
        .all()
    )

    since = datetime.now(UTC) - timedelta(days=window_days)
    # Scoped to this project. A dashboard that counts one reviewer's work on
    # another job alongside this one's backlog is comparing two populations.
    rulings = list(
        session.execute(
            select(Ruling)
            .join(ChecklistItem, ChecklistItem.id == Ruling.checklist_item_id)
            .join(Asset, Asset.id == ChecklistItem.asset_id)
            .where(Asset.project_id == project_id, Ruling.created_at >= since)
        )
        .scalars()
        .all()
    )
    users = {
        u.id: u
        for u in session.execute(
            select(AppUser).where(
                AppUser.id.in_({r.reviewer_id for r in rulings} or {uuid.uuid4()})
            )
        )
        .scalars()
        .all()
    }

    by_reviewer: dict[uuid.UUID, list[Ruling]] = {}
    for ruling in rulings:
        by_reviewer.setdefault(ruling.reviewer_id, []).append(ruling)

    stats: list[ReviewerStats] = []
    for reviewer_id, their in by_reviewer.items():
        user = users.get(reviewer_id)
        passes = [r for r in their if r.verdict is Verdict.PASS]
        with_note = [r for r in passes if r.note and len(r.note.strip()) >= MEANINGFUL_NOTE_CHARS]
        stats.append(
            ReviewerStats(
                reviewer_id=reviewer_id,
                display_name=user.display_name if user else "(unknown)",
                rulings=len(their),
                passes=len(passes),
                fails=sum(1 for r in their if r.verdict is Verdict.FAIL),
                recaptures=sum(
                    1 for r in their if r.verdict_reason is VerdictReason.RECAPTURE_REQUESTED
                ),
                notes_on_passes=len(with_note),
                labeling_rate=(len(with_note) / len(passes)) if passes else 1.0,
            )
        )
    stats.sort(key=lambda s: s.rulings, reverse=True)

    return Dashboard(
        awaiting_review=len(waiting),
        safety_awaiting_review=sum(1 for e in waiting if e.criticality is Criticality.SAFETY),
        undelivered=delivery.undelivered,
        undelivered_failures=delivery.undelivered_failures,
        unresolved_assets=unresolved,
        reviewers=stats,
    )
