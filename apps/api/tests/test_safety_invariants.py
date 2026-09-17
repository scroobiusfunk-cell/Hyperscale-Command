"""The rules CLAUDE.md calls non-negotiable, tested against the real schema.

These run against a migrated Postgres, not model metadata, because the guards
they exercise exist only in the migration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AppUser,
    Asset,
    ChecklistItem,
    LabeledExample,
    Project,
    Ruling,
    SourceDocument,
)
from app.models.enums import (
    ChecklistItemState,
    Criticality,
    CxAlloyDeliveryState,
    RequirementStatus,
    RulingVerdict,
    UserRole,
)
from tests import factories as f


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def document(db: Session, project: Project) -> SourceDocument:
    return f.make_document(db, project)


@pytest.fixture
def asset(db: Session, project: Project) -> Asset:
    return f.make_asset(db, project)


@pytest.fixture
def reviewer(db: Session) -> AppUser:
    return f.make_user(db, UserRole.REVIEWER)


class TestSafetyNeverAutoClears:
    """The rule the whole system is built around."""

    def test_safety_item_cannot_be_auto_cleared(
        self, db: Session, project: Project, document: SourceDocument, asset: Asset
    ) -> None:
        requirement = f.make_requirement(
            db,
            project,
            document,
            criticality=Criticality.SAFETY,
            why_it_matters=(
                "Without the label, someone opening this board cannot know what "
                "protective equipment they need."
            ),
        )
        with pytest.raises(DBAPIError, match="criticality safety"):
            f.make_checklist_item(db, asset, requirement, state=ChecklistItemState.AUTO_CLEARED)

    def test_safety_item_cannot_be_updated_into_auto_cleared(
        self, db: Session, project: Project, document: SourceDocument, asset: Asset
    ) -> None:
        """Blocking the insert is not enough if an update can walk it in later."""
        requirement = f.make_requirement(
            db,
            project,
            document,
            criticality=Criticality.SAFETY,
            why_it_matters=(
                "Without the label, someone opening this board cannot know what "
                "protective equipment they need."
            ),
        )
        item = f.make_checklist_item(db, asset, requirement, state=ChecklistItemState.ROUTED)
        item.state = ChecklistItemState.AUTO_CLEARED
        with pytest.raises(DBAPIError, match="criticality safety"):
            db.flush()

    def test_non_safety_item_can_be_auto_cleared(
        self, db: Session, project: Project, document: SourceDocument, asset: Asset
    ) -> None:
        """Control: the guard is about criticality, not a blanket ban."""
        requirement = f.make_requirement(db, project, document, criticality=Criticality.QUALITY)
        item = f.make_checklist_item(db, asset, requirement, state=ChecklistItemState.AUTO_CLEARED)
        assert item.state is ChecklistItemState.AUTO_CLEARED


class TestRulingsAreAppendOnly:
    """A correction is a new ruling, never an edit to the old one."""

    @pytest.fixture
    def ruling(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        asset: Asset,
        reviewer: AppUser,
    ) -> Ruling:
        requirement = f.make_requirement(db, project, document)
        item = f.make_checklist_item(db, asset, requirement)
        ruling = Ruling(
            checklist_item_id=item.id,
            verdict=RulingVerdict.PASS,
            note="Label present and readable.",
            reviewer_id=reviewer.id,
        )
        db.add(ruling)
        db.flush()
        return ruling

    def test_ruling_cannot_be_updated(self, db: Session, ruling: Ruling) -> None:
        ruling.verdict = RulingVerdict.FAIL
        with pytest.raises(DBAPIError, match="append-only"):
            db.flush()

    def test_ruling_cannot_be_deleted(self, db: Session, ruling: Ruling) -> None:
        db.delete(ruling)
        with pytest.raises(DBAPIError, match="append-only"):
            db.flush()

    def test_correction_is_a_new_ruling_and_both_survive(
        self, db: Session, ruling: Ruling, reviewer: AppUser
    ) -> None:
        correction = Ruling(
            checklist_item_id=ruling.checklist_item_id,
            verdict=RulingVerdict.FAIL,
            note="On a second look the label is for the wrong voltage.",
            reviewer_id=reviewer.id,
            supersedes=ruling.id,
        )
        db.add(correction)
        db.flush()

        rulings = db.query(Ruling).filter_by(checklist_item_id=ruling.checklist_item_id).all()
        assert len(rulings) == 2
        original = next(r for r in rulings if r.supersedes is None)
        assert original.verdict is RulingVerdict.PASS, "the original ruling must stay readable"
        assert correction.supersedes == original.id

    def test_labeled_example_cannot_be_updated(
        self, db: Session, ruling: Ruling, reviewer: AppUser
    ) -> None:
        """Training data that can be rewritten after the fact is evidence of nothing."""
        item = db.query(ChecklistItem).filter_by(id=ruling.checklist_item_id).one()
        example = LabeledExample(
            ruling_id=ruling.id,
            checklist_item_id=item.id,
            requirement_id=item.requirement_id,
            evidence_ids=[],
            item_type="visual_presence.label",
            human_verdict=RulingVerdict.PASS,
            human_note="Label present and readable.",
            reviewer_id=reviewer.id,
            labeled_at=datetime.now(UTC),
        )
        db.add(example)
        db.flush()

        example.human_note = "Actually I was not sure."
        with pytest.raises(DBAPIError, match="append-only"):
            db.flush()


class TestNothingClearsAnonymously:
    def test_reviewer_passed_requires_a_named_resolver(
        self, db: Session, project: Project, document: SourceDocument, asset: Asset
    ) -> None:
        requirement = f.make_requirement(db, project, document)
        with pytest.raises(IntegrityError, match="ck_checklist_item_ruling_names_a_person"):
            f.make_checklist_item(db, asset, requirement, state=ChecklistItemState.REVIEWER_PASSED)

    def test_reviewer_passed_with_a_named_resolver_is_accepted(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        asset: Asset,
        reviewer: AppUser,
    ) -> None:
        requirement = f.make_requirement(db, project, document)
        item = f.make_checklist_item(
            db,
            asset,
            requirement,
            state=ChecklistItemState.REVIEWER_PASSED,
            reviewer=reviewer.id,
            resolved_by=reviewer.id,
            resolved_at=datetime.now(UTC),
        )
        assert item.resolved_by == reviewer.id

    def test_blocked_requires_a_reason(
        self, db: Session, project: Project, document: SourceDocument, asset: Asset
    ) -> None:
        """Silent deferral is the failure the architecture doc names."""
        requirement = f.make_requirement(db, project, document)
        with pytest.raises(IntegrityError, match="ck_checklist_item_blocked_has_reason"):
            f.make_checklist_item(db, asset, requirement, state=ChecklistItemState.BLOCKED)

    def test_delivery_cannot_be_confirmed_by_nobody(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        asset: Asset,
        reviewer: AppUser,
    ) -> None:
        """CxAlloy is read only; only a person can confirm a ruling landed there."""
        requirement = f.make_requirement(db, project, document)
        with pytest.raises(
            IntegrityError, match="ck_checklist_item_delivery_confirmed_by_a_person"
        ):
            f.make_checklist_item(
                db,
                asset,
                requirement,
                state=ChecklistItemState.REVIEWER_PASSED,
                reviewer=reviewer.id,
                resolved_by=reviewer.id,
                resolved_at=datetime.now(UTC),
                cxalloy_delivery_state=CxAlloyDeliveryState.DELIVERY_CONFIRMED,
            )


class TestIdempotency:
    def test_regenerating_an_area_cannot_duplicate_checklist_items(
        self, db: Session, project: Project, document: SourceDocument, asset: Asset
    ) -> None:
        """Items are generated lazily per area; generating twice must be safe."""
        requirement = f.make_requirement(db, project, document)
        f.make_checklist_item(db, asset, requirement)
        with pytest.raises(IntegrityError, match="uq_checklist_item_asset_requirement_ruleset"):
            f.make_checklist_item(db, asset, requirement)

    def test_a_retried_upload_cannot_duplicate_evidence(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        asset: Asset,
        reviewer: AppUser,
    ) -> None:
        """Field app writes are idempotent by client-generated id."""
        requirement = f.make_requirement(db, project, document)
        item = f.make_checklist_item(db, asset, requirement)
        recipe = f.make_capture_recipe(db)
        client_id = uuid.uuid4()
        f.make_evidence(db, item, recipe, reviewer, client_id=client_id)
        with pytest.raises(IntegrityError, match="uq_evidence_client_id"):
            f.make_evidence(db, item, recipe, reviewer, client_id=client_id)


class TestRequirementCuration:
    def test_safety_requirement_needs_a_real_reason(
        self, db: Session, project: Project, document: SourceDocument
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_requirement_safety_has_real_reason"):
            f.make_requirement(
                db, project, document, criticality=Criticality.SAFETY, why_it_matters="Safety."
            )

    def test_approved_requirement_needs_something_to_capture(
        self, db: Session, project: Project, document: SourceDocument
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_requirement_approved_has_evidence_spec"):
            f.make_requirement(
                db, project, document, status=RequirementStatus.APPROVED, evidence_spec=[]
            )

    def test_draft_requirement_may_have_nothing_to_capture_yet(
        self, db: Session, project: Project, document: SourceDocument
    ) -> None:
        requirement = f.make_requirement(
            db, project, document, status=RequirementStatus.DRAFT, evidence_spec=[]
        )
        assert requirement.evidence_spec == []
