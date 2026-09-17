"""The reconciler against a real database.

Two properties matter most here and both are about re-running an import, which
is the normal case rather than the exception: the equipment list gets re-pulled
from CxAlloy on a schedule, and every pull re-observes every tag.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppUser, Asset, AssetAlias, Project, ReconciliationQueueItem
from app.models.enums import AliasSource, ReconciliationStatus, UserRole
from app.models.reconciliation import ReconciliationQueueReason, ReconciliationQueueStatus
from app.reconciliation.matcher import MatchOutcome, TagObservation
from app.reconciliation.service import (
    open_queue_size,
    reconcile,
    resolve_queue_item,
)
from tests import factories as f


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def switchboard(db: Session, project: Project) -> Asset:
    asset = f.make_asset(db, project, tag="SWBD-101")
    asset.reconciliation_status = ReconciliationStatus.UNRESOLVED
    db.flush()
    return asset


@pytest.fixture
def curator(db: Session) -> AppUser:
    return f.make_user(db, UserRole.CURATOR)


def observation(
    tag: str = "SWBD 101",
    source: AliasSource = AliasSource.CXALLOY,
    equipment_class: str | None = "switchboard",
    room: str | None = None,
) -> TagObservation:
    return TagObservation(
        raw_tag=tag, source=source, equipment_class=equipment_class, location_room=room
    )


def aliases_of(db: Session, asset_id: uuid.UUID) -> list[AssetAlias]:
    return list(
        db.execute(select(AssetAlias).where(AssetAlias.asset_id == asset_id)).scalars().all()
    )


class TestAutoMatching:
    def test_a_confident_match_records_the_variant_as_an_alias(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        result = reconcile(db, project.id, observation("SWBD 101"))

        assert result.decision.is_auto_match
        assert result.asset_id == switchboard.id
        assert not result.queued

        aliases = aliases_of(db, switchboard.id)
        assert [a.value for a in aliases] == ["SWBD 101"], "the raw value is what gets stored"
        assert aliases[0].normalized_value == "SWBD101"
        assert aliases[0].source is AliasSource.CXALLOY

    def test_matching_marks_the_asset_auto_matched(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        reconcile(db, project.id, observation())
        assert switchboard.reconciliation_status is ReconciliationStatus.AUTO_MATCHED

    def test_a_machine_match_never_downgrades_a_human_decision(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        switchboard.reconciliation_status = ReconciliationStatus.HUMAN_CONFIRMED
        db.flush()

        reconcile(db, project.id, observation("SWBD_101"))

        assert switchboard.reconciliation_status is ReconciliationStatus.HUMAN_CONFIRMED

    def test_reconciling_the_same_observation_twice_adds_one_alias(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        """Re-importing the equipment list must not grow the alias table."""
        reconcile(db, project.id, observation("SWBD 101"))
        reconcile(db, project.id, observation("SWBD 101"))

        assert len(aliases_of(db, switchboard.id)) == 1

    def test_the_same_tag_from_a_second_source_is_recorded_separately(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        """Which source said what is the audit trail; collapsing them loses it."""
        reconcile(db, project.id, observation("SWBD 101", source=AliasSource.CXALLOY))
        reconcile(db, project.id, observation("SWBD 101", source=AliasSource.DRAWING_SCHEDULE))

        sources = {a.source for a in aliases_of(db, switchboard.id)}
        assert sources == {AliasSource.CXALLOY, AliasSource.DRAWING_SCHEDULE}


class TestQueueing:
    def test_an_unmatched_tag_goes_to_the_queue_and_creates_no_asset(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        before = db.execute(select(Asset.id)).scalars().all()

        result = reconcile(db, project.id, observation("AHU-7"))

        assert result.queued
        assert result.asset_id is None
        assert db.execute(select(Asset.id)).scalars().all() == before, (
            "the reconciler must never invent an asset"
        )

    def test_the_queue_entry_says_why_and_shows_what_was_considered(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        f.make_asset(db, project, tag="SWBD-102")
        result = reconcile(db, project.id, observation("SWBD-10"))

        item = db.get(ReconciliationQueueItem, result.queue_item_id)
        assert item is not None
        assert item.reason is ReconciliationQueueReason.AMBIGUOUS
        assert item.explanation
        assert len(item.candidates) == 2
        assert {c["asset_id"] for c in item.candidates} != set()
        assert item.raw_tag == "SWBD-10", "the raw value is preserved for the person reading it"

    def test_re_running_an_import_does_not_grow_the_queue(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        first = reconcile(db, project.id, observation("AHU-7"))
        second = reconcile(db, project.id, observation("AHU-7"))

        assert first.queue_item_id == second.queue_item_id
        assert open_queue_size(db, project.id) == 1

    def test_punctuation_variants_of_the_same_tag_share_one_queue_entry(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        reconcile(db, project.id, observation("AHU 7"))
        reconcile(db, project.id, observation("ahu-7"))

        assert open_queue_size(db, project.id) == 1

    def test_a_nameplate_reading_is_queued_even_when_the_tag_is_exact(
        self, db: Session, project: Project, switchboard: Asset
    ) -> None:
        result = reconcile(db, project.id, observation("SWBD-101", source=AliasSource.NAMEPLATE))

        assert result.queued
        assert result.decision.outcome is MatchOutcome.QUEUED_LOW_CONFIDENCE
        assert aliases_of(db, switchboard.id) == [], "an unconfirmed reading is not an alias"

    def test_a_tag_that_later_matches_clears_its_open_queue_entry(
        self, db: Session, project: Project
    ) -> None:
        """The queue is a worklist. Entries that answered themselves must leave it."""
        reconcile(db, project.id, observation("SWBD 101"))
        assert open_queue_size(db, project.id) == 1

        # The asset arrives in a later equipment-list pull.
        f.make_asset(db, project, tag="SWBD-101")
        reconcile(db, project.id, observation("SWBD 101"))

        assert open_queue_size(db, project.id) == 0


class TestAPersonResolvingTheQueue:
    def test_resolution_records_the_alias_and_the_person(
        self, db: Session, project: Project, switchboard: Asset, curator: AppUser
    ) -> None:
        result = reconcile(db, project.id, observation("SB101"))
        assert result.queue_item_id is not None

        item = resolve_queue_item(
            db,
            result.queue_item_id,
            asset_id=switchboard.id,
            resolved_by=curator.id,
        )

        assert item.status is ReconciliationQueueStatus.RESOLVED
        assert item.resolved_asset_id == switchboard.id
        assert item.resolved_by == curator.id
        assert item.resolved_at is not None
        assert [a.value for a in aliases_of(db, switchboard.id)] == ["SB101"]

    def test_resolution_marks_the_asset_human_confirmed(
        self, db: Session, project: Project, switchboard: Asset, curator: AppUser
    ) -> None:
        result = reconcile(db, project.id, observation("SB101"))
        assert result.queue_item_id is not None
        resolve_queue_item(
            db, result.queue_item_id, asset_id=switchboard.id, resolved_by=curator.id
        )

        assert switchboard.reconciliation_status is ReconciliationStatus.HUMAN_CONFIRMED

    def test_a_resolved_entry_leaves_the_open_queue(
        self, db: Session, project: Project, switchboard: Asset, curator: AppUser
    ) -> None:
        result = reconcile(db, project.id, observation("SB101"))
        assert open_queue_size(db, project.id) == 1
        assert result.queue_item_id is not None

        resolve_queue_item(
            db, result.queue_item_id, asset_id=switchboard.id, resolved_by=curator.id
        )

        assert open_queue_size(db, project.id) == 0

    def test_resolving_something_that_does_not_exist_is_an_error(
        self, db: Session, switchboard: Asset, curator: AppUser
    ) -> None:
        with pytest.raises(LookupError):
            resolve_queue_item(db, uuid.uuid4(), asset_id=switchboard.id, resolved_by=curator.id)


class TestQueueSizeMetric:
    def test_queue_size_counts_only_open_entries_in_this_project(
        self, db: Session, project: Project, switchboard: Asset, curator: AppUser
    ) -> None:
        other_project = f.make_project(db, name="Another building")
        f.make_asset(db, other_project, tag="SWBD-900")

        reconcile(db, project.id, observation("AHU-7"))
        reconcile(db, project.id, observation("CHW-2"))
        reconcile(db, other_project.id, observation("AHU-7"))

        assert open_queue_size(db, project.id) == 2
        assert open_queue_size(db, other_project.id) == 1
