"""The curation endpoints over a real database.

These cover the transport decisions — status codes, identity, what a refused
publish looks like to a caller — rather than re-testing the service rules.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Environment, Settings
from app.deps import get_session
from app.main import create_app
from app.models import AppUser, Project, Requirement, RuleSet, SourceDocument
from app.models.enums import Criticality, RequirementStatus, UserRole
from tests import factories as f


@pytest.fixture
def api(db: Session) -> Iterator[TestClient]:
    """An app whose requests run inside the test transaction."""
    app = create_app(Settings(environment=Environment.TEST, auth_dev_identity_enabled=True))
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


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
def draft(db: Session, project: Project) -> RuleSet:
    return f.make_rule_set(db, project, "1.0.0")


def as_user(user: AppUser) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user.id)}


class TestIdentityIsRequired:
    def test_without_sso_configured_the_api_says_so_rather_than_inventing_a_user(
        self, db: Session, draft: RuleSet
    ) -> None:
        app = create_app(Settings(environment=Environment.TEST, auth_dev_identity_enabled=False))
        app.dependency_overrides[get_session] = lambda: db
        with TestClient(app) as client:
            response = client.get(f"/rule-sets/{draft.id}")

        assert response.status_code == 501
        assert "SSO" in response.json()["detail"]

    def test_a_request_with_no_identity_is_rejected(self, api: TestClient, draft: RuleSet) -> None:
        assert api.get(f"/rule-sets/{draft.id}").status_code == 401

    def test_an_unknown_user_is_rejected(self, api: TestClient, draft: RuleSet) -> None:
        response = api.get(
            f"/rule-sets/{draft.id}",
            headers={"X-Dev-User-Id": "00000000-0000-4000-8000-000000000000"},
        )
        assert response.status_code == 401


class TestRuleSetEndpoints:
    def test_creating_a_draft(self, api: TestClient, project: Project, curator: AppUser) -> None:
        response = api.post(
            f"/projects/{project.id}/rule-sets",
            json={"version": "2.0.0"},
            headers=as_user(curator),
        )

        assert response.status_code == 201
        assert response.json()["status"] == "draft"

    def test_a_malformed_version_is_rejected_before_it_reaches_the_service(
        self, api: TestClient, project: Project, curator: AppUser
    ) -> None:
        response = api.post(
            f"/projects/{project.id}/rule-sets",
            json={"version": "two point oh"},
            headers=as_user(curator),
        )
        assert response.status_code == 422

    def test_a_duplicate_version_is_a_conflict(
        self, api: TestClient, project: Project, curator: AppUser, draft: RuleSet
    ) -> None:
        response = api.post(
            f"/projects/{project.id}/rule-sets",
            json={"version": draft.version},
            headers=as_user(curator),
        )
        assert response.status_code == 409

    def test_an_unknown_rule_set_is_a_404(self, api: TestClient, curator: AppUser) -> None:
        response = api.get(
            "/rule-sets/00000000-0000-4000-8000-0000000000ff", headers=as_user(curator)
        )
        assert response.status_code == 404


class TestTheCurationQueue:
    def test_requirements_come_back_safety_first(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        """The curator's attention is the scarce resource."""
        f.make_requirement(db, project, document, rule_set=draft, status=RequirementStatus.DRAFT)
        f.make_requirement(
            db,
            project,
            document,
            rule_set=draft,
            criticality=Criticality.SAFETY,
            status=RequirementStatus.NEEDS_REVIEW,
            why_it_matters="Somebody opening this board needs to know the arc flash rating.",
        )

        body = api.get(f"/rule-sets/{draft.id}/requirements", headers=as_user(curator)).json()

        assert [r["criticality"] for r in body] == ["safety", "quality"]

    def test_the_queue_can_be_filtered_by_status(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        f.make_requirement(db, project, document, rule_set=draft)
        f.make_requirement(
            db, project, document, rule_set=draft, status=RequirementStatus.NEEDS_REVIEW
        )

        body = api.get(
            f"/rule-sets/{draft.id}/requirements",
            params={"status": "needs_review"},
            headers=as_user(curator),
        ).json()

        assert len(body) == 1
        assert body[0]["status"] == "needs_review"

    def test_the_queue_carries_the_source_clause_and_page(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        """A requirement that cannot point at its clause is not curatable."""
        f.make_requirement(db, project, document, rule_set=draft)

        body = api.get(f"/rule-sets/{draft.id}/requirements", headers=as_user(curator)).json()

        assert body[0]["source_clause"]
        assert body[0]["source_page"] >= 1


class TestApprovingAndPublishing:
    def test_approving_then_publishing(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        requirement = f.make_requirement(
            db, project, document, rule_set=draft, status=RequirementStatus.DRAFT
        )

        approved = api.post(
            f"/rule-sets/{draft.id}/requirements/{requirement.id}/approve",
            headers=as_user(curator),
        )
        assert approved.status_code == 200
        assert approved.json()["approved_by"] == str(curator.id)

        published = api.post(f"/rule-sets/{draft.id}/publish", headers=as_user(curator))
        assert published.status_code == 200
        assert published.json()["approved"] == 1

    def test_a_refused_publish_tells_the_caller_every_reason(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        f.make_requirement(
            db,
            project,
            document,
            rule_set=draft,
            criticality=Criticality.SAFETY,
            status=RequirementStatus.NEEDS_REVIEW,
            why_it_matters="Somebody opening this board needs to know the arc flash rating.",
        )

        response = api.post(f"/rule-sets/{draft.id}/publish", headers=as_user(curator))

        assert response.status_code == 409
        reasons = response.json()["detail"]["reasons"]
        assert any("safety" in reason for reason in reasons)
        assert any("nothing to publish" in reason for reason in reasons)

    def test_a_tech_approving_is_a_conflict_not_a_silent_success(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
    ) -> None:
        tech = f.make_user(db, UserRole.TECH)
        requirement = f.make_requirement(
            db, project, document, rule_set=draft, status=RequirementStatus.DRAFT
        )

        response = api.post(
            f"/rule-sets/{draft.id}/requirements/{requirement.id}/approve",
            headers=as_user(tech),
        )

        assert response.status_code == 409
        assert "not a curator" in response.json()["detail"]
        db.refresh(requirement)
        assert requirement.status is RequirementStatus.DRAFT


class TestDiffEndpoint:
    def test_a_revision_reports_what_changed(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        document: SourceDocument,
        curator: AppUser,
    ) -> None:
        base = f.make_rule_set(db, project, "1.0.0")
        head = f.make_rule_set(db, project, "1.1.0")
        f.make_requirement(db, project, document, rule_set=base)
        f.make_requirement(db, project, document, rule_set=head)

        body = api.get(f"/rule-sets/{base.id}/diff/{head.id}", headers=as_user(curator)).json()

        assert body["base_version"] == "1.0.0"
        assert body["head_version"] == "1.1.0"
        assert len(body["added"]) == 1
        assert len(body["removed"]) == 1


class TestConflictEndpoints:
    def _contested_rule_set(
        self, db: Session, project: Project, draft: RuleSet
    ) -> tuple[Requirement, Requirement]:
        from app.models.enums import DocumentType
        from app.requirements_compiler.grouping import compute_check_key

        key = compute_check_key(
            equipment_class=["switchboard"],
            system=None,
            location_type=None,
            check_subject="equipment nameplate",
        )
        made = []
        for _ in range(2):
            document = f.make_document(db, project)
            document.doc_type = DocumentType.SPEC_SECTION
            requirement = f.make_requirement(db, project, document, rule_set=draft)
            requirement.check_key = key
            made.append(requirement)
        db.flush()
        return made[0], made[1]

    def test_resolving_precedence_reports_what_it_found(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        self._contested_rule_set(db, project, draft)

        body = api.post(
            f"/rule-sets/{draft.id}/resolve-precedence", headers=as_user(curator)
        ).json()

        assert body["contested"] == 1
        assert body["conflicts_opened"] == 1

    def test_conflicts_are_listed_with_what_the_rules_saw(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        self._contested_rule_set(db, project, draft)
        api.post(f"/rule-sets/{draft.id}/resolve-precedence", headers=as_user(curator))

        body = api.get(f"/rule-sets/{draft.id}/conflicts", headers=as_user(curator)).json()

        assert len(body) == 1
        assert body[0]["reason"]
        assert len(body[0]["candidates"]) == 2

    def test_a_curator_picks_the_winner(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        winner, loser = self._contested_rule_set(db, project, draft)
        api.post(f"/rule-sets/{draft.id}/resolve-precedence", headers=as_user(curator))
        conflict_id = api.get(f"/rule-sets/{draft.id}/conflicts", headers=as_user(curator)).json()[
            0
        ]["id"]

        response = api.post(
            f"/rule-sets/{draft.id}/conflicts/{conflict_id}/resolve",
            json={"winner_requirement_id": str(winner.id), "note": "The spec governs."},
            headers=as_user(curator),
        )

        assert response.status_code == 200
        assert response.json()["status"] == "resolved"
        db.refresh(loser)
        assert loser.status is RequirementStatus.RETIRED

    def test_publishing_is_blocked_while_a_conflict_is_open(
        self,
        api: TestClient,
        db: Session,
        project: Project,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        self._contested_rule_set(db, project, draft)
        api.post(f"/rule-sets/{draft.id}/resolve-precedence", headers=as_user(curator))

        response = api.post(f"/rule-sets/{draft.id}/publish", headers=as_user(curator))

        assert response.status_code == 409
        assert any(
            "precedence conflict" in reason for reason in response.json()["detail"]["reasons"]
        )
