"""Applying the field app's event log.

Two properties, both required by CLAUDE.md and both tested directly:

1. **Idempotent by client id.** A retried upload is the normal case on a bad
   connection. The same event applied twice changes nothing the second time, and
   `replay_pending` can be run as often as anyone likes.
2. **The reviewer wins.** "If a reviewer changed an item's state while the tech
   was offline, the reviewer's state wins and the tech's evidence is attached
   rather than applied. The tech is told what changed."

Events are ordered by the device's sequence number, not by its clock. A phone
that has been off for a week comes back with a plausible-looking wrong time, and
ordering evidence by it would interleave two walks nonsensically.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import ChecklistItem, Evidence, Prediction, Requirement, Ruling, SyncEvent
from app.models.enums import ChecklistItemState, EvidenceStatus, PredictedVerdict
from app.models.sync_event import SyncEventStatus, SyncEventType
from app.requirements_compiler.grouping import item_type_of
from app.sync.blobs import evidence_storage_key
from app.sync.events import (
    CaptureTaken,
    EventEnvelope,
    IncomingEvent,
    ItemDeferred,
    payload_of,
)

log = get_logger(__name__)

#: States a reviewer or the policy layer has already decided. A tech's event
#: never moves an item out of one of these.
DECIDED_STATES = frozenset(
    {
        ChecklistItemState.REVIEWER_PASSED,
        ChecklistItemState.REVIEWER_FAILED,
        ChecklistItemState.AUTO_CLEARED,
    }
)


@dataclass(frozen=True)
class ChangedWhileYouWereAway:
    """Something the tech needs to be told about when they get back in signal."""

    checklist_item_id: uuid.UUID
    message: str


@dataclass(frozen=True)
class SyncResult:
    accepted: int = 0
    duplicates: int = 0
    """Events already stored from an earlier upload. Not an error."""
    applied: int = 0
    superseded: int = 0
    rejected: int = 0
    evidence_created: int = 0
    tell_the_tech: tuple[ChangedWhileYouWereAway, ...] = field(default=())

    @property
    def clean(self) -> bool:
        return self.rejected == 0


def _store_incoming(
    session: Session, submitted_by: uuid.UUID, events: list[IncomingEvent]
) -> tuple[list[SyncEvent], int]:
    """Persist events we have not seen, skipping the ones we have."""
    incoming_ids = {e.client_event_id for e in events}
    already = {
        row.client_event_id
        for row in session.execute(
            select(SyncEvent).where(SyncEvent.client_event_id.in_(incoming_ids))
        )
        .scalars()
        .all()
    }

    stored: list[SyncEvent] = []
    seen_in_batch: set[uuid.UUID] = set()
    now = datetime.now(UTC)

    for event in events:
        if event.client_event_id in already or event.client_event_id in seen_in_batch:
            continue
        seen_in_batch.add(event.client_event_id)
        row = SyncEvent(
            client_event_id=event.client_event_id,
            client_walk_id=event.client_walk_id,
            sequence=event.sequence,
            event_type=event.event_type,
            checklist_item_id=event.checklist_item_id,
            payload=payload_of(event),
            occurred_at=event.occurred_at,
            received_at=now,
            submitted_by=submitted_by,
            status=SyncEventStatus.PENDING,
        )
        session.add(row)
        stored.append(row)

    session.flush()
    return stored, len(events) - len(stored)


def _apply_capture(
    session: Session, row: SyncEvent, item: ChecklistItem
) -> tuple[bool, str | None]:
    """Create the evidence, unless it is already there.

    Returns (created, note). Evidence is attached whatever state the item is in:
    a reviewer having already ruled does not make the photo worthless, and
    throwing it away would lose the one thing the tech actually did.
    """
    try:
        capture = CaptureTaken.model_validate(
            {
                "event_type": SyncEventType.CAPTURE_TAKEN,
                "client_event_id": row.client_event_id,
                "client_walk_id": row.client_walk_id,
                "sequence": row.sequence,
                "occurred_at": row.occurred_at,
                "checklist_item_id": row.checklist_item_id,
                **row.payload,
            }
        )
    except ValidationError as exc:
        return False, f"The capture event did not parse: {exc.error_count()} problem(s)."

    existing = session.execute(
        select(Evidence).where(Evidence.client_id == capture.client_id)
    ).scalar_one_or_none()
    if existing is not None:
        return False, None

    retake_of: uuid.UUID | None = None
    if capture.retake_of_client_id is not None:
        previous = session.execute(
            select(Evidence).where(Evidence.client_id == capture.retake_of_client_id)
        ).scalar_one_or_none()
        if previous is not None:
            retake_of = previous.id
            previous.status = EvidenceStatus.SUPERSEDED

    session.add(
        Evidence(
            client_id=capture.client_id,
            checklist_item_id=item.id,
            capture_recipe_id=capture.capture_recipe_id,
            capture_recipe_version=capture.capture_recipe_version,
            step_index=capture.step_index,
            media_type=capture.media_type,
            # Derived here, not taken from the device, and the row stays
            # pending until the bytes actually turn up. See app/sync/blobs.py.
            storage_key=evidence_storage_key(capture.client_id),
            content_hash=capture.content_hash,
            byte_size=capture.byte_size,
            mime_type=capture.mime_type,
            captured_at=capture.occurred_at,
            received_at=row.received_at,
            captured_by=row.submitted_by,
            device_metadata=capture.device_metadata.model_dump(mode="json"),
            gate_results=[g.model_dump(mode="json") for g in capture.gate_results],
            retake_of=retake_of,
            status=EvidenceStatus.PENDING_UPLOAD,
        )
    )
    return True, None


def _apply_prediction(
    session: Session, row: SyncEvent, item: ChecklistItem
) -> tuple[SyncEventStatus, str | None, bool, ChangedWhileYouWereAway | None]:
    """Record the learner's own call, but only if the answer is not out yet.

    This is the guard the whole agreement metric rests on. A device controls its
    own clock and its own event order, so "the learner predicted before the
    reveal" cannot be taken on the device's word. The server checks its own
    record instead: if this item already carries a ruling, the call arrives too
    late to mean anything and is refused rather than stored.
    """
    payload = row.payload or {}
    verdict_value = payload.get("verdict")
    try:
        verdict = PredictedVerdict(str(verdict_value))
    except ValueError:
        return (
            SyncEventStatus.REJECTED,
            f"Not a verdict a learner can make: {verdict_value!r}.",
            False,
            None,
        )

    already_ruled = session.execute(
        select(Ruling.id).where(Ruling.checklist_item_id == item.id).limit(1)
    ).scalar_one_or_none()
    if already_ruled is not None:
        return (
            SyncEventStatus.REJECTED,
            "This item had already been ruled on, so a call recorded now would not "
            "be a prediction.",
            False,
            None,
        )

    existing = session.execute(
        select(Prediction).where(
            Prediction.checklist_item_id == item.id,
            Prediction.predicted_by == row.submitted_by,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # One call per person per item. A retake does not reopen a judgement
        # about the installation, and the row could not be changed anyway.
        return SyncEventStatus.SUPERSEDED, "You had already made a call on this one.", False, None

    requirement = session.get(Requirement, (item.requirement_id, item.ruleset_version))
    session.add(
        Prediction(
            checklist_item_id=item.id,
            predicted_by=row.submitted_by,
            verdict=verdict,
            reason=(payload.get("reason") or None),
            note=(payload.get("note") or None),
            item_type=item_type_of(requirement),
        )
    )
    return SyncEventStatus.APPLIED, None, False, None


def _apply_one(
    session: Session, row: SyncEvent
) -> tuple[SyncEventStatus, str | None, bool, ChangedWhileYouWereAway | None]:
    """Apply one event. Returns (status, note, evidence_created, tell_the_tech)."""
    if row.event_type is SyncEventType.WALK_COMPLETED:
        return SyncEventStatus.APPLIED, None, False, None

    if row.checklist_item_id is None:
        return SyncEventStatus.REJECTED, "The event names no checklist item.", False, None

    item = session.get(ChecklistItem, row.checklist_item_id)
    if item is None:
        return (
            SyncEventStatus.REJECTED,
            "That checklist item does not exist. It may belong to a rule set version "
            "that has been replaced.",
            False,
            None,
        )

    decided = item.state in DECIDED_STATES
    created = False
    note: str | None = None

    if row.event_type is SyncEventType.CAPTURE_TAKEN:
        created, failure = _apply_capture(session, row, item)
        if failure is not None:
            return SyncEventStatus.REJECTED, failure, False, None

    if row.event_type is SyncEventType.PREDICTION_MADE:
        return _apply_prediction(session, row, item)

    if row.event_type in (SyncEventType.ITEM_OPENED, SyncEventType.GATE_FAILED):
        # Recorded, not acted on. Time-on-item and gate-failure rate are the
        # Phase 1 signals these exist for.
        return SyncEventStatus.APPLIED, None, created, None

    if decided:
        # The reviewer wins. Evidence is already attached above; the state
        # change is not applied, and the tech is told.
        return (
            SyncEventStatus.SUPERSEDED,
            f"A reviewer had already set this item to {item.state.value}.",
            created,
            ChangedWhileYouWereAway(
                checklist_item_id=item.id,
                message=(
                    f"While you were offline a reviewer marked this "
                    f"{item.state.value.replace('_', ' ')}. Your photos are attached to it."
                ),
            ),
        )

    if row.event_type is SyncEventType.ITEM_CAPTURED:
        item.state = ChecklistItemState.EVIDENCE_CAPTURED
        return SyncEventStatus.APPLIED, note, created, None

    if row.event_type is SyncEventType.ITEM_DEFERRED:
        try:
            deferred = ItemDeferred.model_validate(
                {
                    "event_type": SyncEventType.ITEM_DEFERRED,
                    "client_event_id": row.client_event_id,
                    "client_walk_id": row.client_walk_id,
                    "sequence": row.sequence,
                    "occurred_at": row.occurred_at,
                    "checklist_item_id": row.checklist_item_id,
                    **row.payload,
                }
            )
        except ValidationError:
            return SyncEventStatus.REJECTED, "The deferral event did not parse.", created, None

        item.state = ChecklistItemState.BLOCKED
        item.blocked_reason = deferred.reason
        item.blocked_note = deferred.note
        item.blocked_at = row.occurred_at
        return SyncEventStatus.APPLIED, note, created, None

    return SyncEventStatus.APPLIED, note, created, None


def _apply_pending(session: Session, rows: list[SyncEvent]) -> SyncResult:
    applied = superseded = rejected = evidence_created = 0
    messages: list[ChangedWhileYouWereAway] = []
    now = datetime.now(UTC)

    # Device sequence, not device clock: a phone that has been off for a week
    # comes back with a plausible-looking wrong time.
    for row in sorted(rows, key=lambda r: (r.client_walk_id, r.sequence, r.received_at)):
        if row.status is not SyncEventStatus.PENDING:
            continue

        status, note, created, message = _apply_one(session, row)
        row.status = status
        row.outcome_note = note
        row.applied_at = now

        if created:
            evidence_created += 1
        if message is not None:
            messages.append(message)
        if status is SyncEventStatus.APPLIED:
            applied += 1
        elif status is SyncEventStatus.SUPERSEDED:
            superseded += 1
        elif status is SyncEventStatus.REJECTED:
            rejected += 1

    session.flush()
    return SyncResult(
        applied=applied,
        superseded=superseded,
        rejected=rejected,
        evidence_created=evidence_created,
        tell_the_tech=tuple(messages),
    )


def sync(session: Session, *, submitted_by: uuid.UUID, envelope: EventEnvelope) -> SyncResult:
    """Take one upload from a device and apply it."""
    stored, duplicates = _store_incoming(session, submitted_by, envelope.events)
    outcome = _apply_pending(session, stored)

    result = SyncResult(
        accepted=len(stored),
        duplicates=duplicates,
        applied=outcome.applied,
        superseded=outcome.superseded,
        rejected=outcome.rejected,
        evidence_created=outcome.evidence_created,
        tell_the_tech=outcome.tell_the_tech,
    )
    log.info(
        "sync.completed",
        submitted_by=str(submitted_by),
        accepted=result.accepted,
        duplicates=result.duplicates,
        applied=result.applied,
        superseded=result.superseded,
        rejected=result.rejected,
        evidence_created=result.evidence_created,
    )
    return result


def replay_pending(session: Session) -> SyncResult:
    """Re-run anything still pending. Safe to run as often as you like."""
    pending = list(
        session.execute(select(SyncEvent).where(SyncEvent.status == SyncEventStatus.PENDING))
        .scalars()
        .all()
    )
    return _apply_pending(session, pending)
