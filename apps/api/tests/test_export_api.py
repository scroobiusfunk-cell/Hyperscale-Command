"""The export endpoints over HTTP: build, download, confirm.

The reviewer console's Delivery page described this whole workflow — build a
package, work through it in CxAlloy, confirm it here — and offered no way to do
any of it. Worse, there was no route serving the package at all, so "work
through it" was not possible even by hand. These cover the round trip the page
now performs, and the permission that had been missing from all of it.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Environment, Settings
from app.deps import get_session, get_storage
from app.main import create_app
from app.models import AppUser, Project
from app.models.enums import UserRole
from app.storage import InMemoryStorage
from tests import factories as f
from tests.test_cxalloy_export import a_ruled_item


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
def reviewer(db: Session) -> AppUser:
    return f.make_user(db, UserRole.REVIEWER)


def who(user: AppUser) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user.id)}


class TestTheRoundTrip:
    def test_build_download_confirm(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        reviewer: AppUser,
    ) -> None:
        """What the Delivery page does, in the order it does it."""
        a_ruled_item(db, project, reviewer)

        built = api.post(f"/projects/{project.id}/exports", headers=who(reviewer))
        assert built.status_code == 201
        package = built.json()
        assert package["item_count"] == 1
        assert package["has_file"] is True
        assert package["confirmed_at"] is None

        file = api.get(f"/exports/{package['id']}/file", headers=who(reviewer))
        assert file.status_code == 200
        assert file.headers["content-type"] == "application/zip"
        assert ".zip" in file.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(file.content)) as archive:
            assert any(name.endswith(".csv") for name in archive.namelist())

        before = api.get(f"/projects/{project.id}/delivery-status", headers=who(reviewer)).json()
        assert before["exported_not_confirmed"] == 1

        confirmed = api.post(f"/exports/{package['id']}/confirm-delivery", headers=who(reviewer))
        assert confirmed.status_code == 200
        assert confirmed.json()["confirmed_at"] is not None

        after = api.get(f"/projects/{project.id}/delivery-status", headers=who(reviewer)).json()
        assert after["exported_not_confirmed"] == 0
        assert after["undelivered"] == 0

    def test_the_list_shows_what_was_built(
        self, api: TestClient, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        a_ruled_item(db, project, reviewer)
        api.post(f"/projects/{project.id}/exports", headers=who(reviewer))

        listed = api.get(f"/projects/{project.id}/exports", headers=who(reviewer))

        assert listed.status_code == 200
        assert [row["item_count"] for row in listed.json()] == [1]
        assert listed.json()[0]["created_at"]


class TestAnEmptyPackage:
    def test_building_with_nothing_waiting_is_allowed(
        self, api: TestClient, project: Project, reviewer: AppUser
    ) -> None:
        built = api.post(f"/projects/{project.id}/exports", headers=who(reviewer))

        assert built.status_code == 201
        assert built.json()["item_count"] == 0
        assert built.json()["has_file"] is False

    def test_but_there_is_nothing_to_download(
        self, api: TestClient, project: Project, reviewer: AppUser
    ) -> None:
        """Offering a download for an empty package would be a lie about it."""
        built = api.post(f"/projects/{project.id}/exports", headers=who(reviewer)).json()

        response = api.get(f"/exports/{built['id']}/file", headers=who(reviewer))

        assert response.status_code == 404
        assert "empty" in response.json()["detail"]


class TestWhoMayHandleThem:
    """A package is every ruling on the job in one file. It was open to anyone."""

    def test_a_tech_cannot_build_one(self, api: TestClient, db: Session, project: Project) -> None:
        tech = f.make_user(db, UserRole.TECH)
        assert api.post(f"/projects/{project.id}/exports", headers=who(tech)).status_code == 404

    def test_a_tech_cannot_download_one(
        self, api: TestClient, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        a_ruled_item(db, project, reviewer)
        built = api.post(f"/projects/{project.id}/exports", headers=who(reviewer)).json()
        tech = f.make_user(db, UserRole.TECH)

        response = api.get(f"/exports/{built['id']}/file", headers=who(tech))

        assert response.status_code == 404
        assert "not yours" in response.json()["detail"]

    def test_a_tech_cannot_confirm_delivery(
        self, api: TestClient, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        """Confirming is an assertion about the system of record, for everybody."""
        a_ruled_item(db, project, reviewer)
        built = api.post(f"/projects/{project.id}/exports", headers=who(reviewer)).json()
        tech = f.make_user(db, UserRole.TECH)

        response = api.post(f"/exports/{built['id']}/confirm-delivery", headers=who(tech))

        assert response.status_code == 404

    def test_an_admin_may(self, api: TestClient, db: Session, project: Project) -> None:
        admin = f.make_user(db, UserRole.ADMIN)
        assert api.post(f"/projects/{project.id}/exports", headers=who(admin)).status_code == 201

    def test_a_deactivated_reviewer_may_not(
        self, api: TestClient, db: Session, project: Project, reviewer: AppUser
    ) -> None:
        """Refused before the route, at sign-in: a closed account is not a caller.

        `may_handle_exports` checks `is_active` too, and that belt is worth
        keeping — it is the one thing that still holds if this helper is ever
        called from somewhere that resolved a user another way.
        """
        reviewer.is_active = False
        db.flush()
        assert api.post(f"/projects/{project.id}/exports", headers=who(reviewer)).status_code == 401

    def test_signing_in_is_still_required(self, api: TestClient, project: Project) -> None:
        assert api.post(f"/projects/{project.id}/exports").status_code == 401


class TestWhenSomethingIsMissing:
    def test_no_such_package(self, api: TestClient, reviewer: AppUser) -> None:
        response = api.get(f"/exports/{uuid.uuid4()}/file", headers=who(reviewer))

        assert response.status_code == 404
        assert "not yours" in response.json()["detail"]

    def test_a_package_whose_file_is_gone(
        self,
        api: TestClient,
        db: Session,
        storage: InMemoryStorage,
        project: Project,
        reviewer: AppUser,
    ) -> None:
        """Says so, rather than serving an empty zip somebody would try to import."""
        a_ruled_item(db, project, reviewer)
        built = api.post(f"/projects/{project.id}/exports", headers=who(reviewer)).json()
        storage.objects.clear()

        response = api.get(f"/exports/{built['id']}/file", headers=who(reviewer))

        assert response.status_code == 404
        assert "not in storage" in response.json()["detail"]
