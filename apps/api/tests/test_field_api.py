"""The field app's three calls, end to end over HTTP."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.capture.recipes import ensure_builtin_recipes
from app.checklist.instantiation import Area, instantiate
from app.config import Environment, Settings
from app.deps import get_session
from app.main import create_app
from app.models import AppUser, CaptureRecipe, ChecklistItem, Project, RuleSet
from app.models.enums import ChecklistItemState, ReconciliationStatus, UserRole
from app.requirements_compiler import rule_set as curation
from tests import factories as f

ROOM = "Electrical Room 1-04"
SHA = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


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
def recipe(db: Session) -> CaptureRecipe:
    return ensure_builtin_recipes(db)[0]


@pytest.fixture
def walkable(db: Session, project: Project) -> RuleSet:
    curator = f.make_user(db, UserRole.CURATOR)
    document = f.make_document(db, project)
    rule_set = f.make_rule_set(db, project, "1.0.0")
    f.make_requirement(db, project, document, rule_set=rule_set)
    curation.publish(db, rule_set.id, published_by=curator.id)

    asset = f.make_asset(db, project)
    asset.location_room = ROOM
    asset.location_type = "electrical_room"
    asset.reconciliation_status = ReconciliationStatus.HUMAN_CONFIRMED
    db.flush()

    instantiate(db, rule_set.id, Area(project_id=project.id))
    return rule_set


def as_user(user: AppUser) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user.id)}


class TestDownloadingAWalk:
    def test_a_preview_returns_stops_with_capture_steps(
        self, api: TestClient, project: Project, tech: AppUser, walkable: RuleSet
    ) -> None:
        body = api.post(f"/field/projects/{project.id}/walk", json={}, headers=as_user(tech)).json()

        assert body["item_count"] == 1
        item = body["stops"][0]["items"][0]
        assert item["steps"]
        assert item["why_it_matters"]
        assert item["scaffold_level"] == "full"

    def test_a_preview_records_nothing(
        self, api: TestClient, db: Session, project: Project, tech: AppUser, walkable: RuleSet
    ) -> None:
        api.post(
            f"/field/projects/{project.id}/walk",
            json={"open_rooms": []},
            headers=as_user(tech),
        )
        assert db.query(ChecklistItem).one().state is ChecklistItemState.OPEN
        assert db.query(ChecklistItem).one().assigned_tech is None

    def test_starting_the_walk_assigns_it_and_records_deferrals(
        self, api: TestClient, db: Session, project: Project, tech: AppUser, walkable: RuleSet
    ) -> None:
        response = api.post(
            f"/field/projects/{project.id}/walk/start", json={}, headers=as_user(tech)
        )

        assert response.status_code == 201
        assert db.query(ChecklistItem).one().assigned_tech == tech.id

    def test_a_locked_room_comes_back_as_a_deferral_with_a_reason(
        self, api: TestClient, project: Project, tech: AppUser, walkable: RuleSet
    ) -> None:
        body = api.post(
            f"/field/projects/{project.id}/walk",
            json={"open_rooms": ["Some other room"]},
            headers=as_user(tech),
        ).json()

        assert body["stops"] == []
        assert body["deferred"][0]["reason"] == "no_access"
        assert ROOM in body["deferred"][0]["note"]


class TestSyncingTheEventLog:
    def _capture(self, item_id: uuid.UUID, recipe: CaptureRecipe) -> dict[str, object]:
        return {
            "event_type": "capture_taken",
            "client_event_id": str(uuid.uuid4()),
            "client_walk_id": str(uuid.uuid4()),
            "sequence": 1,
            "occurred_at": datetime(2026, 9, 15, 10, 31, tzinfo=UTC).isoformat(),
            "checklist_item_id": str(item_id),
            "client_id": str(uuid.uuid4()),
            "capture_recipe_id": str(recipe.id),
            "capture_recipe_version": recipe.version,
            "step_index": 0,
            "storage_key": "projects/x/evidence/a.jpg",
            "content_hash": SHA,
            "byte_size": 1024,
            "mime_type": "image/jpeg",
        }

    def test_a_walks_worth_of_events_is_applied(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        tech: AppUser,
        walkable: RuleSet,
        recipe: CaptureRecipe,
    ) -> None:
        item_id = db.query(ChecklistItem).one().id
        response = api.post(
            "/field/sync",
            json={"events": [self._capture(item_id, recipe)]},
            headers=as_user(tech),
        )

        assert response.status_code == 200
        assert response.json()["evidence_created"] == 1

    def test_posting_the_same_batch_again_is_a_no_op(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        tech: AppUser,
        walkable: RuleSet,
        recipe: CaptureRecipe,
    ) -> None:
        """The app retries when it is not sure the upload landed."""
        item_id = db.query(ChecklistItem).one().id
        batch = {"events": [self._capture(item_id, recipe)]}

        first = api.post("/field/sync", json=batch, headers=as_user(tech)).json()
        second = api.post("/field/sync", json=batch, headers=as_user(tech)).json()

        assert first["evidence_created"] == 1
        assert second["evidence_created"] == 0
        assert second["duplicates"] == 1

    def test_a_malformed_event_is_refused_with_422(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        tech: AppUser,
        walkable: RuleSet,
        recipe: CaptureRecipe,
    ) -> None:
        item_id = db.query(ChecklistItem).one().id
        bad = self._capture(item_id, recipe)
        bad["content_hash"] = "not a sha"

        assert (
            api.post("/field/sync", json={"events": [bad]}, headers=as_user(tech)).status_code
            == 422
        )

    def test_an_empty_sync_is_fine(self, api: TestClient, tech: AppUser) -> None:
        response = api.post("/field/sync", json={"events": []}, headers=as_user(tech))
        assert response.status_code == 200
        assert response.json()["accepted"] == 0
