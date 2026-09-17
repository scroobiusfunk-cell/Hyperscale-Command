"""Checklist item instantiation, lazily, per area."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.checklist.instantiation import Area, InstantiationError, instantiate
from app.models import AppUser, Asset, ChecklistItem, Project, RuleSet, SourceDocument
from app.models.enums import (
    ChecklistItemState,
    Criticality,
    ReconciliationStatus,
    RequirementStatus,
    UserRole,
)
from app.requirements_compiler import rule_set as curation
from tests import factories as f


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def document(db: Session, project: Project) -> SourceDocument:
    return f.make_document(db, project)


@pytest.fixture
def curator(db: Session) -> AppUser:
    return f.make_user(db, UserRole.CURATOR)


@pytest.fixture
def published(db: Session, project: Project, document: SourceDocument, curator: AppUser) -> RuleSet:
    """A published rule set with one approved switchboard requirement."""
    rule_set = f.make_rule_set(db, project, "1.0.0")
    f.make_requirement(db, project, document, rule_set=rule_set)
    curation.publish(db, rule_set.id, published_by=curator.id)
    return rule_set


def an_asset(
    db: Session,
    project: Project,
    *,
    tag: str = "SWBD-101",
    equipment_class: str = "switchboard",
    system: str = "normal_power",
    room: str | None = "Electrical Room 1-04",
    location_type: str | None = "electrical_room",
    status: ReconciliationStatus = ReconciliationStatus.HUMAN_CONFIRMED,
) -> Asset:
    asset = f.make_asset(db, project, tag=tag)
    asset.equipment_class = equipment_class
    asset.system = system
    asset.location_room = room
    asset.location_type = location_type
    asset.reconciliation_status = status
    db.flush()
    return asset


class TestOnlyPublishedRuleSetsGenerateWork:
    def test_a_draft_rule_set_is_refused(
        self, db: Session, project: Project, document: SourceDocument
    ) -> None:
        """A draft is a curator's working copy, not a walk."""
        draft = f.make_rule_set(db, project, "2.0.0")
        f.make_requirement(db, project, document, rule_set=draft)
        an_asset(db, project)

        with pytest.raises(InstantiationError, match="draft"):
            instantiate(db, draft.id, Area(project_id=project.id))

    def test_a_published_rule_set_generates_items(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        an_asset(db, project)
        report = instantiate(db, published.id, Area(project_id=project.id))

        assert report.created == 1
        assert db.query(ChecklistItem).count() == 1

    def test_generated_items_start_open_and_carry_the_rule_set_version(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        an_asset(db, project)
        instantiate(db, published.id, Area(project_id=project.id))

        item = db.query(ChecklistItem).one()
        assert item.state is ChecklistItemState.OPEN
        assert item.ruleset_version == published.version


class TestWhatAppliesToWhat:
    def test_an_asset_of_another_class_gets_nothing(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        an_asset(db, project, tag="AHU-7", equipment_class="air_handler")
        assert instantiate(db, published.id, Area(project_id=project.id)).created == 0

    def test_the_system_must_match_when_the_requirement_names_one(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        an_asset(db, project, system="ups_output")
        assert instantiate(db, published.id, Area(project_id=project.id)).created == 0

    def test_system_matching_ignores_spelling_of_separators(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        """CxAlloy says "normal power"; the spec says "normal_power"."""
        an_asset(db, project, system="normal power")
        assert instantiate(db, published.id, Area(project_id=project.id)).created == 1

    def test_the_location_type_must_match_when_the_requirement_names_one(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        an_asset(db, project, location_type="corridor")
        assert instantiate(db, published.id, Area(project_id=project.id)).created == 0

    def test_an_asset_with_no_location_type_does_not_match_a_scoped_requirement(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        an_asset(db, project, location_type=None)
        assert instantiate(db, published.id, Area(project_id=project.id)).created == 0

    def test_a_requirement_with_no_system_applies_to_every_system(
        self, db: Session, project: Project, document: SourceDocument, curator: AppUser
    ) -> None:
        """A null system on the requirement is a wildcard, per the doc."""
        rule_set = f.make_rule_set(db, project, "3.0.0")
        requirement = f.make_requirement(db, project, document, rule_set=rule_set)
        requirement.applies_to_system = None
        requirement.applies_to_location_type = None
        db.flush()
        curation.publish(db, rule_set.id, published_by=curator.id)

        an_asset(db, project, system="anything at all", location_type="a roof")

        assert instantiate(db, rule_set.id, Area(project_id=project.id)).created == 1


class TestWhatIsSkipped:
    def test_an_unresolved_asset_is_skipped_and_counted(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        """Nobody has confirmed this asset exists as described."""
        an_asset(db, project, status=ReconciliationStatus.UNRESOLVED)

        report = instantiate(db, published.id, Area(project_id=project.id))

        assert report.created == 0
        assert report.assets_skipped_unresolved == 1
        assert report.needs_reconciliation_first

    def test_an_auto_matched_asset_is_walkable(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        an_asset(db, project, status=ReconciliationStatus.AUTO_MATCHED)
        assert instantiate(db, published.id, Area(project_id=project.id)).created == 1

    def test_unapproved_requirements_do_not_instantiate(
        self, db: Session, project: Project, document: SourceDocument, curator: AppUser
    ) -> None:
        rule_set = f.make_rule_set(db, project, "4.0.0")
        f.make_requirement(db, project, document, rule_set=rule_set)
        f.make_requirement(
            db, project, document, rule_set=rule_set, status=RequirementStatus.NEEDS_REVIEW
        )
        curation.publish(db, rule_set.id, published_by=curator.id)
        an_asset(db, project)

        report = instantiate(db, rule_set.id, Area(project_id=project.id))

        assert report.requirements_considered == 1
        assert report.created == 1


class TestLazinessAndRepeats:
    def test_only_the_named_room_is_generated(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        """Tens of thousands of items is why this is per area."""
        an_asset(db, project, tag="SWBD-101", room="Electrical Room 1-04")
        an_asset(db, project, tag="SWBD-201", room="Electrical Room 2-01")

        report = instantiate(
            db, published.id, Area(project_id=project.id, room="Electrical Room 1-04")
        )

        assert report.created == 1
        assert db.query(ChecklistItem).count() == 1

    def test_a_named_set_of_assets_can_be_generated(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        wanted = an_asset(db, project, tag="SWBD-101")
        an_asset(db, project, tag="SWBD-201", room="Electrical Room 2-01")

        report = instantiate(
            db, published.id, Area(project_id=project.id, asset_ids=frozenset({wanted.id}))
        )

        assert report.created == 1

    def test_walking_the_same_area_twice_creates_nothing_the_second_time(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        an_asset(db, project)
        area = Area(project_id=project.id)

        first = instantiate(db, published.id, area)
        second = instantiate(db, published.id, area)

        assert first.created == 1
        assert second.created == 0
        assert second.already_present == 1
        assert db.query(ChecklistItem).count() == 1

    def test_an_area_with_no_assets_is_not_an_error(
        self, db: Session, project: Project, published: RuleSet
    ) -> None:
        report = instantiate(
            db, published.id, Area(project_id=project.id, room="A room with nothing in it")
        )
        assert report.created == 0
        assert report.assets_matched == 0

    def test_a_new_rule_set_version_generates_its_own_items(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        curator: AppUser,
        published: RuleSet,
    ) -> None:
        """Items record which rule set generated them; a revision is new work."""
        an_asset(db, project)
        instantiate(db, published.id, Area(project_id=project.id))

        revision = curation.create_draft(db, project.id, "1.1.0", supersedes_id=published.id)
        f.make_requirement(db, project, document, rule_set=revision)
        curation.publish(db, revision.id, published_by=curator.id)

        report = instantiate(db, revision.id, Area(project_id=project.id))

        assert report.created == 1
        assert db.query(ChecklistItem).count() == 2
        assert {i.ruleset_version for i in db.query(ChecklistItem).all()} == {"1.0.0", "1.1.0"}


class TestSafetyItemsAreInstantiatedLikeAnyOther:
    def test_a_safety_requirement_produces_a_checklist_item(
        self, db: Session, project: Project, document: SourceDocument, curator: AppUser
    ) -> None:
        """Safety items are walked and captured; what differs is who rules on them."""
        rule_set = f.make_rule_set(db, project, "5.0.0")
        requirement = f.make_requirement(
            db,
            project,
            document,
            rule_set=rule_set,
            criticality=Criticality.SAFETY,
            why_it_matters="Somebody opening this board needs to know the arc flash rating.",
        )
        curation.publish(db, rule_set.id, published_by=curator.id)
        an_asset(db, project)

        instantiate(db, rule_set.id, Area(project_id=project.id))

        item = db.query(ChecklistItem).one()
        assert item.requirement_id == requirement.id
        assert item.state is ChecklistItemState.OPEN
