"""Offline sync and event replay.

The fourth subsystem CLAUDE.md requires tests for before merge. Two properties
carry the weight: replaying is safe to do twice, and a reviewer's decision beats
a tech's event that was made before they knew about it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.capture.recipes import ensure_builtin_recipes
from app.models import AppUser, CaptureRecipe, ChecklistItem, Evidence, Project, SyncEvent
from app.models.enums import (
    BlockedReason,
    ChecklistItemState,
    EvidenceStatus,
    UserRole,
)
from app.models.sync_event import SyncEventStatus, SyncEventType
from app.sync.events import EventEnvelope
from app.sync.replay import replay_pending, sync
from tests import factories as f

SHA = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
WALK = uuid.UUID("aaaa0000-0000-4000-8000-000000000001")


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def tech(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


@pytest.fixture
def reviewer(db: Session) -> AppUser:
    return f.make_user(db, UserRole.REVIEWER)


@pytest.fixture
def recipe(db: Session) -> CaptureRecipe:
    return ensure_builtin_recipes(db)[0]


@pytest.fixture
def item(db: Session, project: Project) -> ChecklistItem:
    document = f.make_document(db, project)
    rule_set = f.make_rule_set(db, project, "1.0.0")
    requirement = f.make_requirement(db, project, document, rule_set=rule_set)
    asset = f.make_asset(db, project)
    return f.make_checklist_item(db, asset, requirement)


def capture_event(
    item: ChecklistItem,
    recipe: CaptureRecipe,
    *,
    client_event_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    sequence: int = 1,
    retake_of: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "event_type": SyncEventType.CAPTURE_TAKEN.value,
        "client_event_id": str(client_event_id or uuid.uuid4()),
        "client_walk_id": str(WALK),
        "sequence": sequence,
        "occurred_at": (occurred_at or datetime(2026, 9, 15, 10, 31, tzinfo=UTC)).isoformat(),
        "checklist_item_id": str(item.id),
        "client_id": str(client_id or uuid.uuid4()),
        "capture_recipe_id": str(recipe.id),
        "capture_recipe_version": recipe.version,
        "step_index": 0,
        "storage_key": "projects/x/evidence/a.jpg",
        "content_hash": SHA,
        "byte_size": 2841177,
        "mime_type": "image/jpeg",
        "device_metadata": {"model": "Pixel 8", "os_version": "Android 15", "app_version": "0.1"},
        "gate_results": [
            {
                "gate_id": "sharpness_floor",
                "outcome": "passed",
                "measured_value": 184.2,
                "threshold": 120,
            }
        ],
        "retake_of_client_id": str(retake_of) if retake_of else None,
    }


def simple_event(
    event_type: SyncEventType,
    item: ChecklistItem,
    *,
    sequence: int = 2,
    client_event_id: uuid.UUID | None = None,
    **extra: object,
) -> dict[str, object]:
    return {
        "event_type": event_type.value,
        "client_event_id": str(client_event_id or uuid.uuid4()),
        "client_walk_id": str(WALK),
        "sequence": sequence,
        "occurred_at": datetime(2026, 9, 15, 10, 35, tzinfo=UTC).isoformat(),
        "checklist_item_id": str(item.id),
        **extra,
    }


def envelope(*events: dict[str, object]) -> EventEnvelope:
    return EventEnvelope.model_validate({"events": list(events)})


class TestIdempotency:
    """A retried upload is the normal case on a bad connection, not an error."""

    def test_the_same_event_uploaded_twice_is_applied_once(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        event = capture_event(item, recipe)

        first = sync(db, submitted_by=tech.id, envelope=envelope(event))
        second = sync(db, submitted_by=tech.id, envelope=envelope(event))

        assert first.evidence_created == 1
        assert second.evidence_created == 0
        assert second.duplicates == 1
        assert db.query(Evidence).count() == 1
        assert db.query(SyncEvent).count() == 1

    def test_a_duplicate_inside_one_batch_is_stored_once(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        event = capture_event(item, recipe)
        result = sync(db, submitted_by=tech.id, envelope=envelope(event, dict(event)))

        assert result.accepted == 1
        assert result.duplicates == 1
        assert db.query(Evidence).count() == 1

    def test_two_events_reporting_the_same_capture_create_one_evidence(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        """The device retried the upload and generated a new event id for it."""
        client_id = uuid.uuid4()
        first = capture_event(item, recipe, client_id=client_id, sequence=1)
        again = capture_event(item, recipe, client_id=client_id, sequence=2)

        sync(db, submitted_by=tech.id, envelope=envelope(first, again))

        assert db.query(Evidence).count() == 1

    def test_replaying_pending_events_twice_changes_nothing(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        """CLAUDE.md: server-side event replay must be safe to run twice."""
        sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(
                capture_event(item, recipe),
                simple_event(SyncEventType.ITEM_CAPTURED, item),
            ),
        )

        # Force everything back to pending, as a re-run after a crash would find it.
        for row in db.query(SyncEvent).all():
            row.status = SyncEventStatus.PENDING
        db.flush()

        first = replay_pending(db)
        second = replay_pending(db)

        assert first.applied >= 1
        assert second.applied == 0, "nothing was left pending"
        assert db.query(Evidence).count() == 1
        assert db.query(ChecklistItem).one().state is ChecklistItemState.EVIDENCE_CAPTURED


class TestTheReviewerWins:
    def test_a_capture_arriving_after_a_ruling_does_not_reopen_the_item(
        self,
        db: Session,
        tech: AppUser,
        reviewer: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        item.state = ChecklistItemState.REVIEWER_PASSED
        item.reviewer = reviewer.id
        item.resolved_by = reviewer.id
        item.resolved_at = datetime.now(UTC)
        db.flush()

        result = sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(simple_event(SyncEventType.ITEM_CAPTURED, item)),
        )

        assert result.superseded == 1
        assert db.query(ChecklistItem).one().state is ChecklistItemState.REVIEWER_PASSED

    def test_the_evidence_is_still_attached(
        self,
        db: Session,
        tech: AppUser,
        reviewer: AppUser,
        item: ChecklistItem,
        recipe: CaptureRecipe,
    ) -> None:
        """A reviewer having ruled does not make the photo worthless."""
        item.state = ChecklistItemState.REVIEWER_FAILED
        item.reviewer = reviewer.id
        item.resolved_by = reviewer.id
        item.resolved_at = datetime.now(UTC)
        db.flush()

        sync(db, submitted_by=tech.id, envelope=envelope(capture_event(item, recipe)))

        evidence = db.query(Evidence).one()
        assert evidence.checklist_item_id == item.id

    def test_the_tech_is_told_what_changed(
        self, db: Session, tech: AppUser, reviewer: AppUser, item: ChecklistItem
    ) -> None:
        item.state = ChecklistItemState.REVIEWER_PASSED
        item.reviewer = reviewer.id
        item.resolved_by = reviewer.id
        item.resolved_at = datetime.now(UTC)
        db.flush()

        result = sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(simple_event(SyncEventType.ITEM_CAPTURED, item)),
        )

        assert len(result.tell_the_tech) == 1
        message = result.tell_the_tech[0].message
        assert "reviewer" in message
        assert "attached" in message

    def test_a_deferral_does_not_override_a_ruling_either(
        self, db: Session, tech: AppUser, reviewer: AppUser, item: ChecklistItem
    ) -> None:
        item.state = ChecklistItemState.REVIEWER_PASSED
        item.reviewer = reviewer.id
        item.resolved_by = reviewer.id
        item.resolved_at = datetime.now(UTC)
        db.flush()

        sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(
                simple_event(
                    SyncEventType.ITEM_DEFERRED, item, reason=BlockedReason.NO_ACCESS.value
                )
            ),
        )

        assert db.query(ChecklistItem).one().state is ChecklistItemState.REVIEWER_PASSED


class TestOrdering:
    def test_events_are_applied_in_device_sequence_not_arrival_order(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        captured = simple_event(SyncEventType.ITEM_CAPTURED, item, sequence=2)
        deferred = simple_event(
            SyncEventType.ITEM_DEFERRED,
            item,
            sequence=3,
            reason=BlockedReason.NO_ACCESS.value,
            note="Room locked when I came back to finish.",
        )

        # Uploaded out of order, as a batch from a device that retried.
        sync(db, submitted_by=tech.id, envelope=envelope(deferred, captured))

        assert db.query(ChecklistItem).one().state is ChecklistItemState.BLOCKED

    def test_a_device_clock_in_the_past_does_not_reorder_the_walk(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        """A phone that has been off comes back with a plausible wrong time."""
        stale = simple_event(SyncEventType.ITEM_CAPTURED, item, sequence=9)
        stale["occurred_at"] = (datetime.now(UTC) - timedelta(days=400)).isoformat()
        later_defer = simple_event(
            SyncEventType.ITEM_DEFERRED,
            item,
            sequence=2,
            reason=BlockedReason.NO_ACCESS.value,
        )

        sync(db, submitted_by=tech.id, envelope=envelope(stale, later_defer))

        # Sequence 9 is last whatever the clock says.
        assert db.query(ChecklistItem).one().state is ChecklistItemState.EVIDENCE_CAPTURED


class TestBadInputIsRecordedNotDropped:
    def test_an_event_for_an_unknown_item_is_rejected_with_a_reason(
        self, db: Session, tech: AppUser, item: ChecklistItem
    ) -> None:
        orphan = simple_event(SyncEventType.ITEM_CAPTURED, item)
        orphan["checklist_item_id"] = str(uuid.uuid4())

        result = sync(db, submitted_by=tech.id, envelope=envelope(orphan))

        assert result.rejected == 1
        assert not result.clean
        row = db.query(SyncEvent).one()
        assert row.status is SyncEventStatus.REJECTED
        assert "does not exist" in (row.outcome_note or "")

    def test_one_bad_event_does_not_lose_the_rest_of_the_walk(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        """A tech who lost half a walk to a parse failure will not walk it again on trust."""
        orphan = simple_event(SyncEventType.ITEM_CAPTURED, item, sequence=1)
        orphan["checklist_item_id"] = str(uuid.uuid4())
        good = capture_event(item, recipe, sequence=2)

        result = sync(db, submitted_by=tech.id, envelope=envelope(orphan, good))

        assert result.rejected == 1
        assert result.evidence_created == 1

    def test_a_malformed_event_is_refused_at_the_boundary(self) -> None:
        """Strict schemas: a capture with no content hash never reaches the database."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EventEnvelope.model_validate(
                {
                    "events": [
                        {
                            "event_type": "capture_taken",
                            "client_event_id": str(uuid.uuid4()),
                            "client_walk_id": str(WALK),
                            "sequence": 1,
                            "occurred_at": datetime.now(UTC).isoformat(),
                            "checklist_item_id": str(uuid.uuid4()),
                            "client_id": str(uuid.uuid4()),
                            "capture_recipe_id": str(uuid.uuid4()),
                            "capture_recipe_version": "1.0.0",
                            "step_index": 0,
                            "storage_key": "k",
                            "content_hash": "not a sha",
                            "byte_size": 1,
                            "mime_type": "image/jpeg",
                        }
                    ]
                }
            )


class TestWhatTheWalkRecords:
    def test_a_gate_failure_is_recorded_without_evidence(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        """The Phase 1 evidence-quality signal: what the gate caught and the tech retook."""
        result = sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(
                simple_event(
                    SyncEventType.GATE_FAILED,
                    item,
                    sequence=1,
                    capture_recipe_id=str(recipe.id),
                    step_index=0,
                    gate_results=[
                        {
                            "gate_id": "sharpness_floor",
                            "outcome": "failed",
                            "measured_value": 41.0,
                            "threshold": 120,
                        }
                    ],
                )
            ),
        )

        assert result.applied == 1
        assert db.query(Evidence).count() == 0
        assert db.query(SyncEvent).one().payload["gate_results"][0]["outcome"] == "failed"

    def test_a_retake_supersedes_the_shot_it_replaces(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        first_id = uuid.uuid4()
        sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(capture_event(item, recipe, client_id=first_id, sequence=1)),
        )
        sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(capture_event(item, recipe, sequence=2, retake_of=first_id)),
        )

        by_client = {e.client_id: e for e in db.query(Evidence).all()}
        assert by_client[first_id].status is EvidenceStatus.SUPERSEDED
        retake = next(e for e in by_client.values() if e.retake_of is not None)
        assert retake.retake_of == by_client[first_id].id

    def test_opening_an_item_records_time_without_changing_state(
        self, db: Session, tech: AppUser, item: ChecklistItem
    ) -> None:
        sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(simple_event(SyncEventType.ITEM_OPENED, item, sequence=1)),
        )

        assert db.query(ChecklistItem).one().state is ChecklistItemState.OPEN
        assert db.query(SyncEvent).one().status is SyncEventStatus.APPLIED

    def test_a_deferral_from_the_field_records_the_reason(
        self, db: Session, tech: AppUser, item: ChecklistItem
    ) -> None:
        sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(
                simple_event(
                    SyncEventType.ITEM_DEFERRED,
                    item,
                    reason=BlockedReason.ENERGIZED.value,
                    note="Board was live and nobody could shut it down today.",
                )
            ),
        )

        updated = db.query(ChecklistItem).one()
        assert updated.state is ChecklistItemState.BLOCKED
        assert updated.blocked_reason is BlockedReason.ENERGIZED
        assert "live" in (updated.blocked_note or "")

    def test_both_clocks_are_kept_on_the_evidence(
        self, db: Session, tech: AppUser, item: ChecklistItem, recipe: CaptureRecipe
    ) -> None:
        sync(db, submitted_by=tech.id, envelope=envelope(capture_event(item, recipe)))

        evidence = db.query(Evidence).one()
        assert evidence.captured_at < evidence.received_at

    def test_a_walk_completed_event_needs_no_item(self, db: Session, tech: AppUser) -> None:
        result = sync(
            db,
            submitted_by=tech.id,
            envelope=envelope(
                {
                    "event_type": SyncEventType.WALK_COMPLETED.value,
                    "client_event_id": str(uuid.uuid4()),
                    "client_walk_id": str(WALK),
                    "sequence": 99,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "items_attempted": 12,
                }
            ),
        )
        assert result.applied == 1
        assert result.clean
