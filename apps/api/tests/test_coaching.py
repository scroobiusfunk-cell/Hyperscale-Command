"""The teaching loop's return path.

The thing being protected: a reviewer's note is written once and has to reach
the person who took the photograph. Before this existed the note went into the
database and stopped there, so most of these tests are about it arriving.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capture.recipes import ensure_builtin_recipes
from app.coaching.service import my_work
from app.config import Environment, Settings
from app.deps import get_session
from app.main import create_app
from app.models import AppUser, CaptureRecipe, ChecklistItem, Project
from app.models.enums import ChecklistItemState, Criticality, UserRole, Verdict
from app.review import service as review
from tests import factories as f


@pytest.fixture
def api(db: Session) -> Iterator[TestClient]:
    app = create_app(Settings(environment=Environment.TEST, auth_dev_identity_enabled=True))
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def tech(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


@pytest.fixture
def reviewer(db: Session) -> AppUser:
    return f.make_user(db, UserRole.REVIEWER)


def make_item(
    db: Session,
    project: Project,
    *,
    criticality: Criticality = Criticality.QUALITY,
    statement: str = "Every spare breaker position has a filler plate fitted.",
    tag: str = "PNL-1A",
) -> ChecklistItem:
    document = f.make_document(db, project)
    rule_set = f.make_rule_set(db, project, f"1.{uuid.uuid4().int % 9999}.0")
    requirement = f.make_requirement(
        db, project, document, rule_set=rule_set, criticality=criticality, statement=statement
    )
    asset = f.make_asset(db, project, tag=tag)
    return f.make_checklist_item(
        db,
        asset,
        requirement,
        ruleset_version=rule_set.version,
        state=ChecklistItemState.EVIDENCE_CAPTURED,
    )


def capture_by(db: Session, item: ChecklistItem, tech: AppUser) -> None:
    ensure_builtin_recipes(db)
    recipe = db.execute(select(CaptureRecipe).limit(1)).scalars().one()
    f.make_evidence(db, item, recipe, tech)


class TestTheNoteArrives:
    def test_a_tech_sees_the_ruling_on_their_own_capture(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        item = make_item(db, project)
        capture_by(db, item, tech)
        review.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=Verdict.FAIL,
            note="Two positions on the lower left bank are still open.",
        )

        result = my_work(db, tech_id=tech.id)

        assert result.tally.ruled == 1
        assert result.feedback[0].verdict is Verdict.FAIL
        assert "lower left bank" in (result.feedback[0].note or "")

    def test_the_note_arrives_with_the_rule_it_came_from(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        """A correction without the requirement beside it teaches nothing."""
        item = make_item(db, project, statement="Circuit directory is typed and fitted.")
        capture_by(db, item, tech)
        review.rule(db, item.id, reviewer_id=reviewer.id, verdict=Verdict.FAIL, note="Handwritten.")

        entry = my_work(db, tech_id=tech.id).feedback[0]

        assert entry.statement == "Circuit directory is typed and fitted."
        assert entry.why_it_matters
        assert entry.asset_tag == "PNL-1A"

    def test_the_reviewer_is_named(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        item = make_item(db, project)
        capture_by(db, item, tech)
        review.rule(db, item.id, reviewer_id=reviewer.id, verdict=Verdict.PASS, note=None)

        assert my_work(db, tech_id=tech.id).feedback[0].reviewer_name == reviewer.display_name

    def test_a_pass_with_a_note_reaches_the_tech_too(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        """Why it was right is the part that generalises to the next board."""
        item = make_item(db, project)
        capture_by(db, item, tech)
        review.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=Verdict.PASS,
            note="Good wide shot — the whole board is readable in one frame.",
        )

        assert "readable in one frame" in (my_work(db, tech_id=tech.id).feedback[0].note or "")


class TestWhoseWorkItIs:
    def test_another_tech_sees_nothing_of_it(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        item = make_item(db, project)
        capture_by(db, item, tech)
        review.rule(db, item.id, reviewer_id=reviewer.id, verdict=Verdict.PASS, note=None)

        other = f.make_user(db, UserRole.TECH)
        assert my_work(db, tech_id=other.id).tally.ruled == 0

    def test_a_tech_with_no_captures_gets_an_empty_record(self, db: Session, tech: AppUser) -> None:
        result = my_work(db, tech_id=tech.id)
        assert result.tally.ruled == 0
        assert result.feedback == ()

    def test_work_can_be_narrowed_to_one_project(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        mine = make_item(db, project)
        capture_by(db, mine, tech)
        review.rule(db, mine.id, reviewer_id=reviewer.id, verdict=Verdict.PASS, note=None)

        elsewhere = make_item(db, f.make_project(db))
        capture_by(db, elsewhere, tech)
        review.rule(db, elsewhere.id, reviewer_id=reviewer.id, verdict=Verdict.PASS, note=None)

        assert my_work(db, tech_id=tech.id).tally.ruled == 2
        assert my_work(db, tech_id=tech.id, project_id=project.id).tally.ruled == 1


class TestWhatComesFirst:
    def test_work_to_redo_comes_before_the_lessons(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        """A recapture is a job. A tech who does not see it will not go back."""
        passed = make_item(db, project, tag="A-1")
        failed = make_item(db, project, tag="A-2")
        redo = make_item(db, project, tag="A-3")
        for item in (passed, failed, redo):
            capture_by(db, item, tech)
        review.rule(db, passed.id, reviewer_id=reviewer.id, verdict=Verdict.PASS, note=None)
        review.rule(
            db, failed.id, reviewer_id=reviewer.id, verdict=Verdict.FAIL, note="Not fitted."
        )
        review.rule(
            db,
            redo.id,
            reviewer_id=reviewer.id,
            verdict=Verdict.INDETERMINATE,
            note="Too blurry to read the label.",
        )

        tags = [entry.asset_tag for entry in my_work(db, tech_id=tech.id).feedback]

        assert tags == ["A-3", "A-2", "A-1"]

    def test_a_recapture_is_flagged_as_needing_another_visit(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        item = make_item(db, project)
        capture_by(db, item, tech)
        review.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=Verdict.INDETERMINATE,
            note="Take it again square on.",
        )

        assert my_work(db, tech_id=tech.id).feedback[0].needs_another_visit is True

    def test_a_pass_does_not_ask_for_another_visit(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        item = make_item(db, project)
        capture_by(db, item, tech)
        review.rule(db, item.id, reviewer_id=reviewer.id, verdict=Verdict.PASS, note=None)

        assert my_work(db, tech_id=tech.id).feedback[0].needs_another_visit is False


class TestCorrections:
    def test_a_correction_replaces_what_the_tech_is_told(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        """Rulings are append-only, but the tech should learn the current answer."""
        item = make_item(db, project, criticality=Criticality.SAFETY)
        capture_by(db, item, tech)
        review.rule(db, item.id, reviewer_id=reviewer.id, verdict=Verdict.FAIL, note="Not fitted.")
        review.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=Verdict.PASS,
            note="My mistake — it is fitted, the angle hid it.",
        )

        feedback = my_work(db, tech_id=tech.id).feedback
        assert len(feedback) == 1
        assert feedback[0].verdict is Verdict.PASS
        assert feedback[0].is_correction is True


class TestTheTally:
    def test_outcomes_are_counted(
        self, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        for verdict, note in (
            (Verdict.PASS, None),
            (Verdict.PASS, None),
            (Verdict.FAIL, "Not fitted."),
            (Verdict.INDETERMINATE, "Too blurry."),
        ):
            item = make_item(db, project, tag=f"A-{uuid.uuid4().hex[:4]}")
            capture_by(db, item, tech)
            review.rule(db, item.id, reviewer_id=reviewer.id, verdict=verdict, note=note)

        tally = my_work(db, tech_id=tech.id).tally

        assert (tally.ruled, tally.passed, tally.failed, tally.recapture_requested) == (4, 2, 1, 1)

    def test_work_still_with_a_reviewer_is_counted_separately(
        self, db: Session, project: Project, tech: AppUser
    ) -> None:
        item = make_item(db, project)
        capture_by(db, item, tech)

        tally = my_work(db, tech_id=tech.id).tally

        assert tally.ruled == 0
        assert tally.awaiting_review == 1


class TestOverHttp:
    def test_a_tech_reads_their_own_record(
        self, api: TestClient, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        item = make_item(db, project)
        capture_by(db, item, tech)
        review.rule(
            db,
            item.id,
            reviewer_id=reviewer.id,
            verdict=Verdict.FAIL,
            note="Two positions still open on the lower bank.",
        )

        response = api.get("/field/my-work", headers={"X-Dev-User-Id": str(tech.id)})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["tally"]["failed"] == 1
        assert "lower bank" in body["feedback"][0]["note"]

    def test_the_record_is_the_caller_s_own_and_not_a_parameter(
        self, api: TestClient, db: Session, project: Project, tech: AppUser, reviewer: AppUser
    ) -> None:
        """Whose work this is comes from the identity, so it cannot be asked for."""
        item = make_item(db, project)
        capture_by(db, item, tech)
        review.rule(db, item.id, reviewer_id=reviewer.id, verdict=Verdict.PASS, note=None)

        other = f.make_user(db, UserRole.TECH)
        body = api.get("/field/my-work", headers={"X-Dev-User-Id": str(other.id)}).json()

        assert body["tally"]["ruled"] == 0
