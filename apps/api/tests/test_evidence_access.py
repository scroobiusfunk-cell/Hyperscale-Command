"""Who may look at a photograph.

Q28: the evidence image route used to check that the caller was a real active
user and nothing else, so any authenticated account could read any evidence in
any project by id. These tests are the fence.

The rule is small enough to state: a reviewer or an admin may look at anything,
because judging evidence is the job; anyone else may look only at what they
captured. The second half is what lets a tech read "too blurry to read the
label" next to the photograph it is about.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import may_view_evidence
from app.capture.recipes import ensure_builtin_recipes
from app.config import Environment, Settings
from app.deps import get_session, get_storage
from app.main import create_app
from app.models import AppUser, CaptureRecipe, ChecklistItem, Evidence, Project
from app.models.enums import ChecklistItemState, UserRole
from app.storage import InMemoryStorage
from app.sync.blobs import evidence_storage_key
from tests import factories as f

BUCKET = "understudy-evidence"
PHOTO = b"\xff\xd8\xff\xe0 the photograph itself"
PHOTO_SHA = hashlib.sha256(PHOTO).hexdigest()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(db: Session, storage: InMemoryStorage) -> Iterator[TestClient]:
    app = create_app(Settings(environment=Environment.TEST, auth_dev_identity_enabled=True))
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def tech(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


def make_item(db: Session, project: Project) -> ChecklistItem:
    document = f.make_document(db, project)
    rule_set = f.make_rule_set(db, project, f"1.{uuid.uuid4().int % 9999}.0")
    requirement = f.make_requirement(db, project, document, rule_set=rule_set)
    return f.make_checklist_item(
        db,
        f.make_asset(db, project),
        requirement,
        ruleset_version=rule_set.version,
        state=ChecklistItemState.EVIDENCE_CAPTURED,
    )


def capture(
    db: Session, storage: InMemoryStorage, project: Project, who: AppUser, *, upload: bool = True
) -> Evidence:
    ensure_builtin_recipes(db)
    recipe = db.execute(select(CaptureRecipe).limit(1)).scalars().one()
    evidence = f.make_evidence(db, make_item(db, project), recipe, who)
    evidence.storage_key = evidence_storage_key(evidence.client_id)
    db.flush()
    if upload:
        storage.put(BUCKET, evidence.storage_key, PHOTO, "image/jpeg")
    return evidence


class TestTheRuleItself:
    def test_a_tech_may_see_their_own(self, db: Session, project: Project, tech: AppUser) -> None:
        evidence = capture(db, InMemoryStorage(), project, tech, upload=False)
        assert may_view_evidence(tech, evidence) is True

    def test_a_tech_may_not_see_somebody_else_s(
        self, db: Session, project: Project, tech: AppUser
    ) -> None:
        evidence = capture(db, InMemoryStorage(), project, tech, upload=False)
        other = f.make_user(db, UserRole.TECH)
        assert may_view_evidence(other, evidence) is False

    def test_a_reviewer_may_see_anything(
        self, db: Session, project: Project, tech: AppUser
    ) -> None:
        evidence = capture(db, InMemoryStorage(), project, tech, upload=False)
        assert may_view_evidence(f.make_user(db, UserRole.REVIEWER), evidence) is True

    def test_an_admin_may_see_anything(self, db: Session, project: Project, tech: AppUser) -> None:
        evidence = capture(db, InMemoryStorage(), project, tech, upload=False)
        assert may_view_evidence(f.make_user(db, UserRole.ADMIN), evidence) is True

    def test_a_curator_is_not_a_reviewer(
        self, db: Session, project: Project, tech: AppUser
    ) -> None:
        """Curating requirements is not a reason to read the field's photographs."""
        evidence = capture(db, InMemoryStorage(), project, tech, upload=False)
        assert may_view_evidence(f.make_user(db, UserRole.CURATOR), evidence) is False

    def test_a_deactivated_reviewer_may_not(
        self, db: Session, project: Project, tech: AppUser
    ) -> None:
        evidence = capture(db, InMemoryStorage(), project, tech, upload=False)
        gone = f.make_user(db, UserRole.REVIEWER)
        gone.is_active = False
        db.flush()
        assert may_view_evidence(gone, evidence) is False


class TestOverHttp:
    def test_a_tech_can_open_their_own_photo(
        self,
        api: TestClient,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        tech: AppUser,
    ) -> None:
        """The point of the whole change: the note lands beside the photograph."""
        evidence = capture(db, storage, project, tech)

        response = api.get(
            f"/evidence/{evidence.id}/image", headers={"X-Dev-User-Id": str(tech.id)}
        )

        assert response.status_code == 200
        assert response.content == PHOTO

    def test_another_tech_is_refused(
        self,
        api: TestClient,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        tech: AppUser,
    ) -> None:
        evidence = capture(db, storage, project, tech)
        other = f.make_user(db, UserRole.TECH)

        response = api.get(
            f"/evidence/{evidence.id}/image", headers={"X-Dev-User-Id": str(other.id)}
        )

        assert response.status_code == 404

    def test_the_refusal_does_not_say_whether_it_exists(
        self,
        api: TestClient,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        tech: AppUser,
    ) -> None:
        """Same answer either way, so the response cannot be used to enumerate."""
        evidence = capture(db, storage, project, tech)
        other = f.make_user(db, UserRole.TECH)
        headers = {"X-Dev-User-Id": str(other.id)}

        refused = api.get(f"/evidence/{evidence.id}/image", headers=headers)
        missing = api.get(f"/evidence/{uuid.uuid4()}/image", headers=headers)

        assert refused.status_code == missing.status_code == 404
        assert refused.json()["detail"] == missing.json()["detail"]

    def test_a_reviewer_can_open_it(
        self,
        api: TestClient,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        tech: AppUser,
    ) -> None:
        evidence = capture(db, storage, project, tech)
        reviewer = f.make_user(db, UserRole.REVIEWER)

        response = api.get(
            f"/evidence/{evidence.id}/image", headers={"X-Dev-User-Id": str(reviewer.id)}
        )

        assert response.status_code == 200
        assert response.content == PHOTO

    def test_a_photo_not_yet_uploaded_says_so_to_its_owner(
        self,
        api: TestClient,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        tech: AppUser,
    ) -> None:
        """Distinct from "not yours": the tech is allowed, the bytes are absent."""
        evidence = capture(db, storage, project, tech, upload=False)

        response = api.get(
            f"/evidence/{evidence.id}/image", headers={"X-Dev-User-Id": str(tech.id)}
        )

        assert response.status_code == 404
        assert "not been uploaded" in response.text

    def test_signing_in_is_still_required(
        self,
        api: TestClient,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        tech: AppUser,
    ) -> None:
        evidence = capture(db, storage, project, tech)
        assert api.get(f"/evidence/{evidence.id}/image").status_code == 401

    def test_the_old_reviewer_only_path_is_gone(
        self,
        api: TestClient,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        tech: AppUser,
    ) -> None:
        """One route, one rule. A second copy is a rule that drifts."""
        evidence = capture(db, storage, project, tech)
        reviewer = f.make_user(db, UserRole.REVIEWER)

        response = api.get(
            f"/review/evidence/{evidence.id}/image", headers={"X-Dev-User-Id": str(reviewer.id)}
        )

        assert response.status_code == 404
