"""The Capture Plan Compiler.

A walk is what a tech actually does, so the tests are mostly about what is left
out of one and why: an item behind a locked door, an item that needs the board
dead, an item nothing knows how to capture.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.capture.recipes import BUILTIN_RECIPES, ensure_builtin_recipes
from app.capture.walk import DeclaredState, compile_walk, start_walk
from app.checklist.instantiation import Area, instantiate
from app.models import AppUser, Asset, CaptureRecipe, ChecklistItem, Project, RuleSet
from app.models.enums import (
    AccessConstraint,
    BlockedReason,
    ChecklistItemState,
    Criticality,
    ReconciliationStatus,
    UserRole,
    VerificationMethod,
)
from app.requirements_compiler import rule_set as curation
from tests import factories as f

ROOM = "Electrical Room 1-04"


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def curator(db: Session) -> AppUser:
    return f.make_user(db, UserRole.CURATOR)


@pytest.fixture
def tech(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


def an_asset(
    db: Session,
    project: Project,
    *,
    tag: str = "SWBD-101",
    room: str | None = ROOM,
    grid_ref: str | None = "C/7",
) -> Asset:
    asset = f.make_asset(db, project, tag=tag)
    asset.location_room = room
    asset.location_grid_ref = grid_ref
    asset.location_type = "electrical_room"
    asset.reconciliation_status = ReconciliationStatus.HUMAN_CONFIRMED
    db.flush()
    return asset


def published_with(
    db: Session,
    project: Project,
    curator: AppUser,
    *,
    version: str = "1.0.0",
    criticality: Criticality = Criticality.QUALITY,
    pass_criteria: dict[str, object] | None = None,
    access_constraints: list[AccessConstraint] | None = None,
    verification_method: VerificationMethod = VerificationMethod.VISUAL,
    statement: str = "The equipment nameplate shows the panel tag.",
) -> RuleSet:
    document = f.make_document(db, project)
    rule_set = f.make_rule_set(db, project, version)
    requirement = f.make_requirement(
        db,
        project,
        document,
        rule_set=rule_set,
        criticality=criticality,
        statement=statement,
        why_it_matters="Somebody opening this board needs to know what is inside it.",
    )
    requirement.pass_criteria = pass_criteria or {
        "kind": "presence",
        "expected": "present",
        "subject": "equipment nameplate",
    }
    requirement.access_constraints = access_constraints or []
    requirement.verification_method = verification_method
    db.flush()
    curation.publish(db, rule_set.id, published_by=curator.id)
    return rule_set


def a_walkable_item(db: Session, project: Project, curator: AppUser, **kwargs: object) -> RuleSet:
    rule_set = published_with(db, project, curator, **kwargs)  # type: ignore[arg-type]
    instantiate(db, rule_set.id, Area(project_id=project.id))
    return rule_set


class TestTheBuiltInRecipes:
    def test_seeding_is_idempotent(self, db: Session) -> None:
        ensure_builtin_recipes(db)
        ensure_builtin_recipes(db)
        assert db.query(CaptureRecipe).count() == len(BUILTIN_RECIPES)

    def test_no_gate_judges_the_content_of_a_photo(self) -> None:
        """Phase 1 gates measure the capture, not what is in it (Q1)."""
        model_gates = {"object_detector", "ocr", "classifier"}
        for recipe in BUILTIN_RECIPES:
            assert not set(recipe.gates) & model_gates

    def test_every_step_reads_as_plain_language(self) -> None:
        for recipe in BUILTIN_RECIPES:
            for step in recipe.steps:
                assert step.instruction[0].isupper() and step.instruction.endswith(".")


class TestAWalkTheTechCanFollow:
    def test_an_open_item_becomes_a_stop_with_capture_steps(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(db, project, curator)

        walk = compile_walk(db, project_id=project.id)

        assert len(walk.stops) == 1
        item = walk.stops[0].items[0]
        assert item.recipe_slug == "visual_presence"
        assert len(item.steps) == 2
        assert item.why_it_matters, "the tech is told why, not just what"

    def test_a_pattern_requirement_gets_the_readable_recipe(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        """Something has to be read, so the capture has to be readable."""
        an_asset(db, project)
        a_walkable_item(
            db,
            project,
            curator,
            pass_criteria={
                "kind": "pattern",
                "pattern": "^[A-Z]{2,4}-[0-9]{2,3}$",
                "description": "The tag reads as letters, a dash, then numbers.",
            },
        )

        walk = compile_walk(db, project_id=project.id)

        assert walk.stops[0].items[0].recipe_slug == "visual_readable"

    def test_stops_are_ordered_by_where_they_are(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project, tag="SWBD-201", room="Electrical Room 2-01", grid_ref="A/1")
        an_asset(db, project, tag="SWBD-101", room=ROOM, grid_ref="C/7")
        a_walkable_item(db, project, curator)

        walk = compile_walk(db, project_id=project.id)

        assert [stop.room for stop in walk.stops] == [ROOM, "Electrical Room 2-01"]

    def test_safety_items_come_first_at_a_stop(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        """A walk cut short should have covered the items that matter most."""
        an_asset(db, project)
        a_walkable_item(db, project, curator, version="1.0.0", statement="Quality check.")
        a_walkable_item(
            db,
            project,
            curator,
            version="2.0.0",
            criticality=Criticality.SAFETY,
            statement="Arc flash label fitted.",
        )

        walk = compile_walk(db, project_id=project.id)

        items = walk.stops[0].items
        assert items[0].is_safety
        assert not items[-1].is_safety

    def test_every_tech_sees_full_scaffolding_in_phase_one(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(db, project, curator)

        walk = compile_walk(db, project_id=project.id)

        assert walk.stops[0].items[0].scaffold_level == "full"


class TestWhatIsDeferredAndWhy:
    def test_a_room_that_is_not_open_defers_its_items(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(db, project, curator)

        walk = compile_walk(
            db,
            project_id=project.id,
            declared=DeclaredState(open_rooms=frozenset({"Electrical Room 2-01"})),
        )

        assert walk.stops == ()
        assert walk.deferred[0].reason is BlockedReason.NO_ACCESS
        assert ROOM in walk.deferred[0].note

    def test_an_energized_room_defers_what_needs_it_dead(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(
            db,
            project,
            curator,
            access_constraints=[AccessConstraint.REQUIRES_DEENERGIZED],
        )

        walk = compile_walk(
            db,
            project_id=project.id,
            declared=DeclaredState(energized_rooms=frozenset({ROOM})),
        )

        assert walk.deferred[0].reason is BlockedReason.ENERGIZED
        assert "dead" in walk.deferred[0].note

    def test_an_energized_room_does_not_defer_what_can_be_done_live(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(db, project, curator)

        walk = compile_walk(
            db,
            project_id=project.id,
            declared=DeclaredState(energized_rooms=frozenset({ROOM})),
        )

        assert walk.item_count == 1
        assert walk.deferred == ()

    def test_no_ladder_defers_what_is_out_of_reach(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(db, project, curator, access_constraints=[AccessConstraint.REQUIRES_LADDER])

        without = compile_walk(db, project_id=project.id, declared=DeclaredState())
        with_ladder = compile_walk(
            db, project_id=project.id, declared=DeclaredState(ladder_available=True)
        )

        assert without.deferred[0].reason is BlockedReason.TOOL_UNAVAILABLE
        assert with_ladder.item_count == 1

    def test_an_asset_with_no_room_is_not_assumed_reachable(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project, room=None)
        a_walkable_item(db, project, curator)

        walk = compile_walk(
            db, project_id=project.id, declared=DeclaredState(open_rooms=frozenset({ROOM}))
        )

        assert walk.deferred[0].reason is BlockedReason.NO_ACCESS
        assert "no room recorded" in walk.deferred[0].note

    def test_a_method_with_no_recipe_is_reported_not_given_the_wrong_one(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        """A tech following capture steps that do not fit produces evidence nobody can rule on."""
        an_asset(db, project)
        a_walkable_item(
            db,
            project,
            curator,
            verification_method=VerificationMethod.MEASURED,
            pass_criteria={
                "kind": "tolerance",
                "nominal": 3.0,
                "plus": 0.5,
                "minus": 0.5,
                "unit": "mm",
            },
        )

        walk = compile_walk(db, project_id=project.id)

        assert walk.stops == ()
        assert len(walk.unroutable) == 1
        assert "measured" in walk.unroutable[0].note


class TestStartingTheWalkRecordsTheDeferrals:
    def test_compiling_alone_changes_nothing(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        """A preview must not mark anything."""
        an_asset(db, project)
        a_walkable_item(db, project, curator)

        compile_walk(db, project_id=project.id, declared=DeclaredState(open_rooms=frozenset()))

        assert db.query(ChecklistItem).one().state is ChecklistItemState.OPEN

    def test_starting_the_walk_blocks_the_deferred_items_with_their_reason(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(db, project, curator)
        walk = compile_walk(
            db, project_id=project.id, declared=DeclaredState(open_rooms=frozenset())
        )

        start_walk(db, walk)

        item = db.query(ChecklistItem).one()
        assert item.state is ChecklistItemState.BLOCKED
        assert item.blocked_reason is BlockedReason.NO_ACCESS
        assert item.blocked_note
        assert item.blocked_at is not None

    def test_starting_the_walk_assigns_the_items_the_tech_will_do(
        self, db: Session, project: Project, curator: AppUser, tech: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(db, project, curator)
        walk = compile_walk(db, project_id=project.id)

        start_walk(db, walk, assigned_tech=tech.id)

        assert db.query(ChecklistItem).one().assigned_tech == tech.id

    def test_an_empty_area_produces_an_empty_walk_rather_than_an_error(
        self, db: Session, project: Project
    ) -> None:
        walk = compile_walk(db, project_id=project.id, room="A room with nothing in it")
        assert walk.stops == ()
        assert walk.item_count == 0

    def test_items_already_captured_are_not_walked_again(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        an_asset(db, project)
        a_walkable_item(db, project, curator)
        item = db.query(ChecklistItem).one()
        item.state = ChecklistItemState.EVIDENCE_CAPTURED
        db.flush()

        assert compile_walk(db, project_id=project.id).item_count == 0


class TestTheRequirementPointsAtItsRecipe:
    """`evidence_spec` is the requirement's own answer to "what must be captured
    to judge it", so the walk follows it rather than re-deriving one."""

    def test_the_walk_uses_the_recipe_the_requirement_points_at(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        from app.capture.recipes import VISUAL_READABLE, evidence_spec_for
        from app.models import Requirement

        an_asset(db, project)
        rule_set = published_with(db, project, curator)
        requirement = db.query(Requirement).filter_by(rule_set_id=rule_set.id).one()
        # Presence criteria, but pointed at the readable recipe on purpose.
        requirement.evidence_spec = evidence_spec_for(db, VISUAL_READABLE)
        db.flush()
        instantiate(db, rule_set.id, Area(project_id=project.id))

        walk = compile_walk(db, project_id=project.id)

        assert walk.stops[0].items[0].recipe_slug == "visual_readable"


class TestCompilationPointsAtARecipe:
    def test_a_compiled_requirement_can_actually_be_approved(
        self, db: Session, project: Project, curator: AppUser
    ) -> None:
        """An approved requirement must have something to capture; compilation
        supplies it, because a curator cannot invent a recipe."""
        from app.ingestion.service import ingest_pdf
        from app.models import Requirement
        from app.models.enums import DocumentType, RequirementStatus
        from app.requirements_compiler.compile import compile_document
        from app.storage import InMemoryStorage
        from tests.pdfs import SPEC_SECTION_LINES, text_pdf
        from tests.test_compile_pipeline import one_requirement_per_section

        document = ingest_pdf(
            db,
            InMemoryStorage(),
            project_id=project.id,
            doc_type=DocumentType.SPEC_SECTION,
            title="26 05 00",
            data=text_pdf([SPEC_SECTION_LINES]),
            bucket="understudy-documents",
        ).document
        rule_set = f.make_rule_set(db, project, "9.0.0")

        compile_document(
            db,
            one_requirement_per_section(),
            document_id=document.id,
            rule_set_id=rule_set.id,
        )

        requirement = db.query(Requirement).filter_by(rule_set_id=rule_set.id).first()
        assert requirement is not None
        assert requirement.evidence_spec, "nothing to capture means it can never be approved"

        curation.approve_requirement(db, requirement.id, rule_set.version, approved_by=curator.id)
        assert requirement.status is RequirementStatus.APPROVED
