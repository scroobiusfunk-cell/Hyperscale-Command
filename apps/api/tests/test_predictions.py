"""Predict-then-reveal: the learner's own call, and whether it can be trusted.

Every test here exists to protect one claim: that the agreement number means
something. A call a learner could make or change after seeing the answer would
turn the whole teaching metric into a flattering fiction, so most of this file
is about refusing calls that arrive too late.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.orm import Session

from app.capture.recipes import ensure_builtin_recipes
from app.coaching.service import agreement
from app.config import Environment, Settings
from app.deps import get_session
from app.main import create_app
from app.models import AppUser, CaptureRecipe, ChecklistItem, Prediction, Project
from app.models.enums import (
    ChecklistItemState,
    PredictedVerdict,
    RulingVerdict,
    UserRole,
)
from app.review import service as review
from app.sync.events import EventEnvelope
from app.sync.replay import sync
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
def learner(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


@pytest.fixture
def senior(db: Session) -> AppUser:
    return f.make_user(db, UserRole.REVIEWER)


def make_item(
    db: Session, project: Project, *, statement: str = "Filler plates are fitted.", tag: str = "P-1"
) -> ChecklistItem:
    document = f.make_document(db, project)
    rule_set = f.make_rule_set(db, project, f"1.{uuid.uuid4().int % 9999}.0")
    requirement = f.make_requirement(db, project, document, rule_set=rule_set, statement=statement)
    return f.make_checklist_item(
        db,
        f.make_asset(db, project, tag=tag),
        requirement,
        ruleset_version=rule_set.version,
        state=ChecklistItemState.EVIDENCE_CAPTURED,
    )


def prediction_event(
    item: ChecklistItem, verdict: str, *, reason: str | None = None
) -> dict[str, object]:
    return {
        "event_type": "prediction_made",
        "client_event_id": str(uuid.uuid4()),
        "client_walk_id": str(uuid.uuid4()),
        "sequence": 0,
        "occurred_at": datetime.now(UTC).isoformat(),
        "checklist_item_id": str(item.id),
        "verdict": verdict,
        "reason": reason,
    }


def predict(db: Session, item: ChecklistItem, who: AppUser, verdict: str, **kw: object) -> None:
    sync(
        db,
        submitted_by=who.id,
        envelope=EventEnvelope.model_validate(
            {"events": [prediction_event(item, verdict, **kw)]}  # type: ignore[arg-type]
        ),
    )


def stored(db: Session, item: ChecklistItem) -> Prediction | None:
    return db.execute(
        select(Prediction).where(Prediction.checklist_item_id == item.id)
    ).scalar_one_or_none()


class TestMakingACall:
    def test_a_call_is_recorded(self, db: Session, project: Project, learner: AppUser) -> None:
        item = make_item(db, project)
        predict(db, item, learner, "fail", reason="plate_missing")

        row = stored(db, item)
        assert row is not None
        assert row.verdict is PredictedVerdict.FAIL
        assert row.reason == "plate_missing"

    def test_unsure_is_a_real_answer(self, db: Session, project: Project, learner: AppUser) -> None:
        """Forcing a binary guess teaches guessing."""
        item = make_item(db, project)
        predict(db, item, learner, "unsure")

        row = stored(db, item)
        assert row is not None
        assert row.verdict is PredictedVerdict.UNSURE

    def test_the_call_is_filed_under_the_kind_of_check(
        self, db: Session, project: Project, learner: AppUser
    ) -> None:
        item = make_item(db, project, statement="Circuit directory is typed.")
        predict(db, item, learner, "pass")

        row = stored(db, item)
        assert row is not None
        assert row.item_type
        assert row.item_type != "unknown"

    def test_a_nonsense_verdict_is_refused(
        self, db: Session, project: Project, learner: AppUser
    ) -> None:
        item = make_item(db, project)
        bad = prediction_event(item, "pass")
        bad["verdict"] = "probably_fine"

        with pytest.raises(ValidationError):
            EventEnvelope.model_validate({"events": [bad]})


class TestCallsThatArriveTooLate:
    def test_a_call_after_the_ruling_is_refused(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        """The guard the whole metric rests on."""
        item = make_item(db, project)
        review.rule(
            db, item.id, reviewer_id=senior.id, verdict=RulingVerdict.FAIL, note="Not fitted."
        )

        predict(db, item, learner, "fail")

        assert stored(db, item) is None

    def test_the_device_cannot_backdate_its_way_around_it(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        """The server checks its own record, not the device's clock."""
        item = make_item(db, project)
        review.rule(db, item.id, reviewer_id=senior.id, verdict=RulingVerdict.PASS, note=None)

        event = prediction_event(item, "pass")
        event["occurred_at"] = "2020-01-01T00:00:00+00:00"
        sync(
            db,
            submitted_by=learner.id,
            envelope=EventEnvelope.model_validate({"events": [event]}),
        )

        assert stored(db, item) is None

    def test_a_second_call_does_not_replace_the_first(
        self, db: Session, project: Project, learner: AppUser
    ) -> None:
        item = make_item(db, project)
        predict(db, item, learner, "pass")
        predict(db, item, learner, "fail")

        row = stored(db, item)
        assert row is not None
        assert row.verdict is PredictedVerdict.PASS

    def test_two_learners_may_each_call_the_same_item(
        self, db: Session, project: Project, learner: AppUser
    ) -> None:
        item = make_item(db, project)
        other = f.make_user(db, UserRole.TECH)
        predict(db, item, learner, "pass")
        predict(db, item, other, "fail")

        rows = (
            db.execute(select(Prediction).where(Prediction.checklist_item_id == item.id))
            .scalars()
            .all()
        )
        assert len(rows) == 2


class TestTheRecordCannotBeEdited:
    def test_the_database_refuses_an_update(
        self, db: Session, project: Project, learner: AppUser
    ) -> None:
        """Enforced by trigger, not by convention."""
        item = make_item(db, project)
        predict(db, item, learner, "pass")
        row = stored(db, item)
        assert row is not None

        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(
                text("UPDATE prediction SET verdict = 'fail' WHERE id = :id"), {"id": row.id}
            )
        db.rollback()

    def test_the_database_refuses_a_delete(
        self, db: Session, project: Project, learner: AppUser
    ) -> None:
        item = make_item(db, project)
        predict(db, item, learner, "pass")
        row = stored(db, item)
        assert row is not None

        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("DELETE FROM prediction WHERE id = :id"), {"id": row.id})
        db.rollback()

    def test_one_call_per_person_per_item_at_the_database_level(
        self, db: Session, project: Project, learner: AppUser
    ) -> None:
        item = make_item(db, project)
        predict(db, item, learner, "pass")

        db.add(
            Prediction(
                checklist_item_id=item.id,
                predicted_by=learner.id,
                verdict=PredictedVerdict.FAIL,
                item_type="whatever",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


class TestAgreement:
    def _call_and_rule(
        self,
        db: Session,
        project: Project,
        learner: AppUser,
        senior: AppUser,
        called: str,
        ruled: RulingVerdict,
        *,
        statement: str = "Filler plates are fitted.",
    ) -> None:
        item = make_item(db, project, statement=statement, tag=f"P-{uuid.uuid4().hex[:4]}")
        predict(db, item, learner, called)
        review.rule(
            db,
            item.id,
            reviewer_id=senior.id,
            verdict=ruled,
            note=None if ruled is RulingVerdict.PASS else "Not fitted.",
        )

    def test_matching_calls_count_as_agreement(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        self._call_and_rule(db, project, learner, senior, "pass", RulingVerdict.PASS)
        self._call_and_rule(db, project, learner, senior, "fail", RulingVerdict.FAIL)

        overall, _ = agreement(db, tech_id=learner.id)

        assert (overall.compared, overall.agreed) == (2, 2)
        assert overall.rate == 1.0

    def test_a_missed_defect_is_counted_apart_from_an_over_call(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        """Calling a defect fine is the dangerous direction and is named."""
        self._call_and_rule(db, project, learner, senior, "pass", RulingVerdict.FAIL)
        self._call_and_rule(db, project, learner, senior, "fail", RulingVerdict.PASS)

        overall, _ = agreement(db, tech_id=learner.id)

        assert overall.missed == 1
        assert overall.over_called == 1
        assert overall.agreed == 0

    def test_catching_a_real_defect_is_counted(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        self._call_and_rule(db, project, learner, senior, "fail", RulingVerdict.FAIL)
        assert agreement(db, tech_id=learner.id)[0].caught == 1

    def test_unsure_is_reported_but_not_scored(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        self._call_and_rule(db, project, learner, senior, "unsure", RulingVerdict.FAIL)
        self._call_and_rule(db, project, learner, senior, "pass", RulingVerdict.PASS)

        overall, _ = agreement(db, tech_id=learner.id)

        assert overall.unsure == 1
        assert overall.compared == 1
        assert overall.rate == 1.0

    def test_a_recapture_cannot_agree_or_disagree(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        """It judges the photograph, not the installation."""
        self._call_and_rule(db, project, learner, senior, "pass", RulingVerdict.RECAPTURE_REQUESTED)

        overall, _ = agreement(db, tech_id=learner.id)

        assert overall.compared == 0
        assert overall.rate is None

    def test_a_recapture_does_not_turn_unsure_into_a_data_point(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        """The same reasoning, one branch further in.

        "I do not know" counted as a reported unsure when the reviewer had only
        asked for the photograph again — so a learner who said the honest thing
        about an item nobody ever ruled on accumulated a record of having been
        unsure about it. Nothing was ever revealed to them, so there is nothing
        to report.
        """
        self._call_and_rule(
            db, project, learner, senior, "unsure", RulingVerdict.RECAPTURE_REQUESTED
        )

        overall, _ = agreement(db, tech_id=learner.id)

        assert overall.unsure == 0
        assert overall.compared == 0
        assert overall.rate is None

    def test_a_check_with_only_a_recapture_is_not_a_row(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        """An all-zero row in the breakdown reads as a result. It is an absence."""
        self._call_and_rule(db, project, learner, senior, "pass", RulingVerdict.RECAPTURE_REQUESTED)

        assert agreement(db, tech_id=learner.id)[1] == ()

    def test_no_rate_when_nothing_is_comparable(self, db: Session, learner: AppUser) -> None:
        """No rate is not the same fact as a rate of zero."""
        overall, per_type = agreement(db, tech_id=learner.id)
        assert overall.rate is None
        assert per_type == ()

    def test_a_correction_is_what_the_learner_is_measured_against(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        item = make_item(db, project)
        predict(db, item, learner, "pass")
        review.rule(
            db, item.id, reviewer_id=senior.id, verdict=RulingVerdict.FAIL, note="Not fitted."
        )
        review.rule(
            db, item.id, reviewer_id=senior.id, verdict=RulingVerdict.PASS, note="My mistake."
        )

        overall, _ = agreement(db, tech_id=learner.id)

        assert overall.agreed == 1
        assert overall.missed == 0

    def test_agreement_is_broken_down_by_kind_of_check(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        self._call_and_rule(
            db, project, learner, senior, "pass", RulingVerdict.PASS, statement="Plates fitted."
        )
        self._call_and_rule(
            db, project, learner, senior, "pass", RulingVerdict.FAIL, statement="Labels legible."
        )

        _, per_type = agreement(db, tech_id=learner.id)

        assert len(per_type) == 2
        assert {a.agreed for a in per_type} == {0, 1}

    def test_another_learner_s_calls_are_not_mine(
        self, db: Session, project: Project, learner: AppUser, senior: AppUser
    ) -> None:
        self._call_and_rule(db, project, learner, senior, "pass", RulingVerdict.PASS)
        other = f.make_user(db, UserRole.TECH)

        assert agreement(db, tech_id=other.id)[0].compared == 0


class TestOverHttp:
    def test_a_learner_sees_their_own_agreement(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        learner: AppUser,
        senior: AppUser,
    ) -> None:
        item = make_item(db, project)
        ensure_builtin_recipes(db)
        recipe = db.execute(select(CaptureRecipe).limit(1)).scalars().one()
        f.make_evidence(db, item, recipe, learner)
        predict(db, item, learner, "pass")
        review.rule(
            db, item.id, reviewer_id=senior.id, verdict=RulingVerdict.FAIL, note="Not fitted."
        )

        body = api.get("/field/my-work", headers={"X-Dev-User-Id": str(learner.id)}).json()

        assert body["agreement"]["compared"] == 1
        assert body["agreement"]["missed"] == 1
        assert body["agreement"]["rate"] == 0.0
        assert len(body["by_item_type"]) == 1
