"""Reviewing: the queue, the one-action ruling, and what gets measured.

The Phase 1 exit metric is earned here, and the flywheel either fills or starves
here, so the tests are mostly about the ruling being one act and the labeling
rate meaning something.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.capture.recipes import ensure_builtin_recipes
from app.models import (
    AppUser,
    CaptureRecipe,
    ChecklistItem,
    LabeledExample,
    Project,
    Ruling,
)
from app.models.enums import (
    ChecklistItemState,
    Criticality,
    CxAlloyDeliveryState,
    RulingVerdict,
    UserRole,
)
from app.review import service
from tests import factories as f


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def reviewer(db: Session) -> AppUser:
    return f.make_user(db, UserRole.REVIEWER)


@pytest.fixture
def tech(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


@pytest.fixture
def recipe(db: Session) -> CaptureRecipe:
    return ensure_builtin_recipes(db)[0]


def an_item_awaiting_review(
    db: Session,
    project: Project,
    *,
    tag: str = "SWBD-101",
    criticality: Criticality = Criticality.QUALITY,
    state: ChecklistItemState = ChecklistItemState.EVIDENCE_CAPTURED,
) -> ChecklistItem:
    document = f.make_document(db, project)
    rule_set = f.make_rule_set(db, project, f"1.{uuid.uuid4().int % 9999}.0")
    requirement = f.make_requirement(
        db,
        project,
        document,
        rule_set=rule_set,
        criticality=criticality,
        why_it_matters="Somebody opening this board needs to know what is inside it.",
    )
    asset = f.make_asset(db, project, tag=tag)
    return f.make_checklist_item(
        db, asset, requirement, ruleset_version=rule_set.version, state=state
    )


class TestTheQueue:
    def test_safety_items_come_first(self, db: Session, project: Project) -> None:
        """A reviewer's attention is the scarce resource the product is built around."""
        an_item_awaiting_review(db, project, tag="SWBD-101")
        an_item_awaiting_review(db, project, tag="SWBD-102", criticality=Criticality.SAFETY)

        entries = service.queue(db, project_id=project.id)

        assert entries[0].criticality is Criticality.SAFETY

    def test_items_not_yet_walked_are_not_in_the_queue(self, db: Session, project: Project) -> None:
        an_item_awaiting_review(db, project, state=ChecklistItemState.OPEN)
        assert service.queue(db, project_id=project.id) == []

    def test_a_ruled_item_leaves_the_queue(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)
        service.rule(db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.PASS, note=None)
        assert service.queue(db, project_id=project.id) == []

    def test_an_item_coming_back_after_a_recapture_is_flagged_as_such(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        """A reviewer should know they have seen this one before."""
        item = an_item_awaiting_review(db, project)
        service.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=RulingVerdict.RECAPTURE_REQUESTED,
            note="Glare across the label, cannot read it.",
        )
        item.state = ChecklistItemState.EVIDENCE_CAPTURED
        db.flush()

        assert service.queue(db, project_id=project.id)[0].is_recapture

    def test_the_queue_counts_the_evidence_waiting(
        self, db: Session, project: Project, tech: AppUser, recipe: CaptureRecipe
    ) -> None:
        item = an_item_awaiting_review(db, project)
        f.make_evidence(db, item, recipe, tech)
        f.make_evidence(db, item, recipe, tech)

        assert service.queue(db, project_id=project.id)[0].evidence_count == 2


class TestRulingIsOneAction:
    def test_a_pass_resolves_the_item_and_names_the_reviewer(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)

        ruling = service.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=RulingVerdict.PASS,
            note="Label present and readable from standing position.",
        )

        assert item.state is ChecklistItemState.REVIEWER_PASSED
        assert item.resolved_by == reviewer.id
        assert ruling.reviewer_id == reviewer.id
        assert ruling.note

    def test_a_ruling_queues_the_result_for_cxalloy(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)
        service.rule(db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.PASS, note=None)
        assert item.cxalloy_delivery_state is CxAlloyDeliveryState.PENDING_EXPORT

    def test_a_fail_without_a_note_is_refused(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        """ "This is wrong" without saying what is wrong is not actionable."""
        item = an_item_awaiting_review(db, project)

        with pytest.raises(service.ReviewError, match="Say what is wrong"):
            service.rule(
                db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.FAIL, note="no"
            )

        assert item.state is ChecklistItemState.EVIDENCE_CAPTURED, "nothing was recorded"

    def test_a_recapture_without_a_note_is_refused(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)
        with pytest.raises(service.ReviewError):
            service.rule(
                db,
                item.id,
                reviewer_id=reviewer.id,
                verdict=RulingVerdict.RECAPTURE_REQUESTED,
                note=" ",
            )

    def test_a_pass_may_be_silent(self, db: Session, project: Project, reviewer: AppUser) -> None:
        """An obvious pass should not need a sentence invented for it."""
        item = an_item_awaiting_review(db, project)
        ruling = service.rule(
            db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.PASS, note=None
        )
        assert ruling.note is None

    def test_a_recapture_sends_the_item_back_rather_than_resolving_it(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)

        service.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=RulingVerdict.RECAPTURE_REQUESTED,
            note="Glare across the label; take it from a slight angle.",
        )

        assert item.state is ChecklistItemState.OPEN
        assert item.resolved_by is None

    def test_only_a_reviewer_may_rule(self, db: Session, project: Project, tech: AppUser) -> None:
        item = an_item_awaiting_review(db, project)
        with pytest.raises(service.ReviewError, match="not a reviewer"):
            service.rule(db, item.id, reviewer_id=tech.id, verdict=RulingVerdict.PASS, note=None)


class TestTheFlywheel:
    def test_a_pass_produces_a_labelled_example(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        """Every reviewer decision becomes a labelled example. This is the Phase 1 output."""
        item = an_item_awaiting_review(db, project)
        service.rule(db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.PASS, note=None)

        example = db.query(LabeledExample).one()
        assert example.checklist_item_id == item.id
        assert example.human_verdict is RulingVerdict.PASS
        assert example.reviewer_id == reviewer.id
        assert example.item_type

    def test_a_fail_produces_one_too(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)
        service.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=RulingVerdict.FAIL,
            note="No label fitted to the front cover.",
        )
        assert db.query(LabeledExample).count() == 1

    def test_a_recapture_produces_none(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        """It is a judgment about the photograph, not about the installation."""
        item = an_item_awaiting_review(db, project)
        service.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=RulingVerdict.RECAPTURE_REQUESTED,
            note="Too far away to read anything.",
        )
        assert db.query(LabeledExample).count() == 0


class TestCorrections:
    def test_a_correction_is_a_new_ruling_pointing_at_the_old_one(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)
        first = service.rule(
            db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.PASS, note=None
        )

        second = service.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=RulingVerdict.FAIL,
            note="On a second look the label is for the wrong voltage.",
        )

        assert second.supersedes == first.id
        assert db.query(Ruling).count() == 2
        assert item.state is ChecklistItemState.REVIEWER_FAILED

    def test_the_original_ruling_is_untouched(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)
        first = service.rule(
            db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.PASS, note=None
        )
        service.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=RulingVerdict.FAIL,
            note="On a second look the label is for the wrong voltage.",
        )

        db.refresh(first)
        assert first.verdict is RulingVerdict.PASS


class TestTheDashboard:
    def test_the_labeling_rate_measures_silent_passes(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        """The number at risk: a reviewer clearing obvious items quickly and silently."""
        for index in range(4):
            item = an_item_awaiting_review(db, project, tag=f"SWBD-{index}")
            service.rule(
                db,
                item.id,
                reviewer_id=reviewer.id,
                verdict=RulingVerdict.PASS,
                note="Label present and readable." if index < 3 else None,
            )

        stats = service.dashboard(db, project_id=project.id).reviewers[0]

        assert stats.passes == 4
        assert stats.notes_on_passes == 3
        assert stats.labeling_rate == pytest.approx(0.75)

    def test_a_short_note_does_not_count_as_labelling(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        """ "ok" tells the next person nothing and tells the flywheel less."""
        item = an_item_awaiting_review(db, project)
        service.rule(db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.PASS, note="ok")

        assert service.dashboard(db, project_id=project.id).reviewers[0].labeling_rate == 0.0

    def test_safety_items_waiting_are_counted_on_their_own(
        self, db: Session, project: Project
    ) -> None:
        an_item_awaiting_review(db, project, tag="SWBD-101")
        an_item_awaiting_review(db, project, tag="SWBD-102", criticality=Criticality.SAFETY)

        board = service.dashboard(db, project_id=project.id)

        assert board.awaiting_review == 2
        assert board.safety_awaiting_review == 1

    def test_undelivered_rulings_are_surfaced(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)
        service.rule(db, item.id, reviewer_id=reviewer.id, verdict=RulingVerdict.PASS, note=None)

        assert service.dashboard(db, project_id=project.id).undelivered == 1


class TestItemDetail:
    def test_the_detail_carries_everything_needed_to_rule(
        self, db: Session, project: Project, tech: AppUser, recipe: CaptureRecipe
    ) -> None:
        item = an_item_awaiting_review(db, project)
        f.make_evidence(db, item, recipe, tech)

        detail = service.item_detail(db, item.id)

        assert detail.statement
        assert detail.why_it_matters, "the reviewer sees why it matters, like the tech does"
        assert detail.source_clause and detail.source_page
        assert detail.pass_criteria
        assert len(detail.evidence) == 1

    def test_the_history_shows_previous_rulings(
        self, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        item = an_item_awaiting_review(db, project)
        service.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=RulingVerdict.RECAPTURE_REQUESTED,
            note="Cannot read the label in this shot.",
        )
        item.state = ChecklistItemState.EVIDENCE_CAPTURED
        db.flush()

        detail = service.item_detail(db, item.id)

        assert len(detail.history) == 1
        assert detail.history[0].verdict is RulingVerdict.RECAPTURE_REQUESTED
