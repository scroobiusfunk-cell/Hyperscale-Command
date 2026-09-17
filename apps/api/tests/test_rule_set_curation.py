"""Curation and versioning.

The rule that matters most here: a rule set containing an unapproved safety
requirement cannot be published, whatever else is true of it. Publishing is the
moment a rule set starts telling techs what to check.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import AppUser, Project, Requirement, RuleSet, RuleSetStatus, SourceDocument
from app.models.enums import Criticality, RequirementStatus, UserRole
from app.requirements_compiler import rule_set as service
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
def tech(db: Session) -> AppUser:
    return f.make_user(db, UserRole.TECH)


@pytest.fixture
def draft(db: Session, project: Project) -> RuleSet:
    return f.make_rule_set(db, project, version="1.0.0")


def a_safety_requirement(
    db: Session, project: Project, document: SourceDocument, rule_set: RuleSet
) -> Requirement:
    return f.make_requirement(
        db,
        project,
        document,
        rule_set=rule_set,
        criticality=Criticality.SAFETY,
        status=RequirementStatus.NEEDS_REVIEW,
        why_it_matters=(
            "Without the label, someone opening this board cannot know what protective "
            "equipment they need."
        ),
    )


class TestCreatingVersions:
    def test_a_draft_starts_unpublished(self, db: Session, project: Project) -> None:
        rule_set = service.create_draft(db, project.id, "1.0.0")
        assert rule_set.status is RuleSetStatus.DRAFT
        assert rule_set.published_by is None

    def test_the_same_version_cannot_be_created_twice(self, db: Session, project: Project) -> None:
        service.create_draft(db, project.id, "1.0.0")
        with pytest.raises(service.CurationError, match="already exists"):
            service.create_draft(db, project.id, "1.0.0")

    def test_two_projects_can_each_have_a_version_one(self, db: Session, project: Project) -> None:
        other = f.make_project(db, name="Another building")
        service.create_draft(db, project.id, "1.0.0")
        service.create_draft(db, other.id, "1.0.0")


class TestApproval:
    def test_approval_records_who_and_when(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        requirement = f.make_requirement(
            db, project, document, rule_set=draft, status=RequirementStatus.DRAFT
        )

        approved = service.approve_requirement(
            db, requirement.id, draft.version, approved_by=curator.id
        )

        assert approved.status is RequirementStatus.APPROVED
        assert approved.approved_by == curator.id
        assert approved.approved_at is not None

    def test_a_tech_cannot_approve_a_requirement(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        tech: AppUser,
    ) -> None:
        requirement = f.make_requirement(
            db, project, document, rule_set=draft, status=RequirementStatus.DRAFT
        )

        with pytest.raises(service.CurationError, match="not a curator"):
            service.approve_requirement(db, requirement.id, draft.version, approved_by=tech.id)

    def test_a_deactivated_curator_cannot_approve(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        curator.is_active = False
        db.flush()
        requirement = f.make_requirement(
            db, project, document, rule_set=draft, status=RequirementStatus.DRAFT
        )

        with pytest.raises(service.CurationError, match="not an active user"):
            service.approve_requirement(db, requirement.id, draft.version, approved_by=curator.id)

    def test_a_published_rule_set_cannot_be_edited(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        """A published set is what the field is walking; changing it is the silent overwrite."""
        approved = f.make_requirement(db, project, document, rule_set=draft)
        service.publish(db, draft.id, published_by=curator.id)

        with pytest.raises(service.CurationError, match="published"):
            service.approve_requirement(db, approved.id, draft.version, approved_by=curator.id)

    def test_rejection_retires_rather_than_deletes(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        """A rejected requirement is evidence about the extraction prompt."""
        requirement = f.make_requirement(
            db, project, document, rule_set=draft, status=RequirementStatus.NEEDS_REVIEW
        )

        rejected = service.reject_requirement(
            db, requirement.id, draft.version, rejected_by=curator.id
        )

        assert rejected.status is RequirementStatus.RETIRED
        assert db.get(Requirement, (requirement.id, draft.version)) is not None


class TestPublishingAndSafety:
    def test_an_unapproved_safety_requirement_blocks_publication(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        f.make_requirement(db, project, document, rule_set=draft)  # an approved quality item
        a_safety_requirement(db, project, document, draft)

        with pytest.raises(service.PublishRefusedError) as raised:
            service.publish(db, draft.id, published_by=curator.id)

        assert any("safety" in reason for reason in raised.value.reasons)
        assert draft.status is RuleSetStatus.DRAFT, "a refused publish leaves the set alone"

    def test_publication_proceeds_once_the_safety_item_is_approved(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        safety = a_safety_requirement(db, project, document, draft)
        service.approve_requirement(db, safety.id, draft.version, approved_by=curator.id)

        summary = service.publish(db, draft.id, published_by=curator.id)

        assert summary.approved == 1
        assert draft.status is RuleSetStatus.PUBLISHED
        assert draft.published_by == curator.id

    def test_a_retired_safety_requirement_does_not_block_publication(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        """Retired means a person looked and decided it does not apply."""
        f.make_requirement(db, project, document, rule_set=draft)
        safety = a_safety_requirement(db, project, document, draft)
        service.reject_requirement(db, safety.id, draft.version, rejected_by=curator.id)

        summary = service.publish(db, draft.id, published_by=curator.id)
        assert summary.approved == 1

    def test_an_empty_rule_set_cannot_be_published(
        self, db: Session, draft: RuleSet, curator: AppUser
    ) -> None:
        with pytest.raises(service.PublishRefusedError, match="nothing to publish"):
            service.publish(db, draft.id, published_by=curator.id)

    def test_publishing_twice_is_refused(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        f.make_requirement(db, project, document, rule_set=draft)
        service.publish(db, draft.id, published_by=curator.id)

        with pytest.raises(service.PublishRefusedError, match="already published"):
            service.publish(db, draft.id, published_by=curator.id)

    def test_a_tech_cannot_publish(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        tech: AppUser,
    ) -> None:
        f.make_requirement(db, project, document, rule_set=draft)
        with pytest.raises(service.CurationError, match="not a curator"):
            service.publish(db, draft.id, published_by=tech.id)

    def test_drafts_left_behind_are_counted_not_published(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        f.make_requirement(db, project, document, rule_set=draft)
        f.make_requirement(db, project, document, rule_set=draft, status=RequirementStatus.DRAFT)

        summary = service.publish(db, draft.id, published_by=curator.id)

        assert summary.approved == 1
        assert summary.left_behind == 1

    def test_publishing_a_revision_supersedes_the_one_it_replaces(
        self,
        db: Session,
        project: Project,
        document: SourceDocument,
        draft: RuleSet,
        curator: AppUser,
    ) -> None:
        f.make_requirement(db, project, document, rule_set=draft)
        service.publish(db, draft.id, published_by=curator.id)

        revision = service.create_draft(db, project.id, "1.1.0", supersedes_id=draft.id)
        f.make_requirement(db, project, document, rule_set=revision)
        service.publish(db, revision.id, published_by=curator.id)

        assert draft.status is RuleSetStatus.SUPERSEDED
        assert revision.status is RuleSetStatus.PUBLISHED


class TestDiffBetweenVersions:
    def test_a_requirement_carried_forward_unchanged_reads_as_unchanged(
        self, db: Session, project: Project, document: SourceDocument
    ) -> None:
        """Requirement ids are stable across versions; that is what makes this work."""
        stable_id = uuid.uuid4()
        recipe = [{"capture_recipe_id": str(uuid.uuid4()), "version": "1.0.0"}]
        base = f.make_rule_set(db, project, "1.0.0")
        head = f.make_rule_set(db, project, "1.1.0")
        f.make_requirement(
            db,
            project,
            document,
            rule_set=base,
            requirement_id=stable_id,
            evidence_spec=recipe,
        )
        f.make_requirement(
            db,
            project,
            document,
            rule_set=head,
            requirement_id=stable_id,
            evidence_spec=recipe,
        )

        result = service.diff(db, base.id, head.id)

        assert result.unchanged == 1
        assert result.is_empty

    def test_a_changed_statement_is_reported_field_by_field(
        self, db: Session, project: Project, document: SourceDocument
    ) -> None:
        stable_id = uuid.uuid4()
        base = f.make_rule_set(db, project, "1.0.0")
        head = f.make_rule_set(db, project, "1.1.0")
        recipe = [{"capture_recipe_id": str(uuid.uuid4()), "version": "1.0.0"}]
        f.make_requirement(
            db,
            project,
            document,
            rule_set=base,
            requirement_id=stable_id,
            statement="The nameplate shows the panel tag.",
            evidence_spec=recipe,
        )
        f.make_requirement(
            db,
            project,
            document,
            rule_set=head,
            requirement_id=stable_id,
            statement="The nameplate shows the panel tag and the voltage.",
            evidence_spec=recipe,
        )

        result = service.diff(db, base.id, head.id)

        assert len(result.changed) == 1
        change = result.changed[0].changes[0]
        assert change.field == "statement"
        assert "voltage" in str(change.after)

    def test_added_and_removed_requirements_are_listed(
        self, db: Session, project: Project, document: SourceDocument
    ) -> None:
        base = f.make_rule_set(db, project, "1.0.0")
        head = f.make_rule_set(db, project, "1.1.0")
        dropped = f.make_requirement(db, project, document, rule_set=base)
        added = f.make_requirement(db, project, document, rule_set=head)

        result = service.diff(db, base.id, head.id)

        assert result.removed == (dropped.id,)
        assert result.added == (added.id,)

    def test_drafts_are_not_part_of_the_diff(
        self, db: Session, project: Project, document: SourceDocument
    ) -> None:
        """A draft never reached the field, so it did not change for anyone."""
        base = f.make_rule_set(db, project, "1.0.0")
        head = f.make_rule_set(db, project, "1.1.0")
        f.make_requirement(db, project, document, rule_set=base)
        f.make_requirement(db, project, document, rule_set=head, status=RequirementStatus.DRAFT)

        result = service.diff(db, base.id, head.id)

        assert result.added == ()
        assert len(result.removed) == 1
