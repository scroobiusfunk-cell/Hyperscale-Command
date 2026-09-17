"""Grouping requirements by what they check, then ranking each group.

The bias throughout: miss a group rather than invent one. A missed group is two
checklist items, which a tech notices. A wrong group silently discards one
document's requirement, and nobody finds out until the rework.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import (
    AppUser,
    ConflictStatus,
    Project,
    Requirement,
    RequirementConflict,
    RuleSet,
    SourceDocument,
)
from app.models.enums import Criticality, DocumentType, RequirementStatus, UserRole
from app.requirements_compiler import rule_set as curation
from app.requirements_compiler.grouping import (
    GroupingError,
    compute_check_key,
    normalize_subject,
    open_conflicts,
    resolve_conflict,
    resolve_precedence,
)
from tests import factories as f


class TestTheCheckKey:
    def test_punctuation_and_spacing_do_not_separate_the_same_subject(self) -> None:
        assert normalize_subject("Name plate") == normalize_subject("nameplate")
        assert normalize_subject("Arc-Flash Warning Label") == normalize_subject(
            "arc flash warning label"
        )

    def test_equipment_class_order_does_not_matter(self) -> None:
        left = compute_check_key(
            equipment_class=["switchboard", "panelboard"],
            system=None,
            location_type=None,
            check_subject="nameplate",
        )
        right = compute_check_key(
            equipment_class=["panelboard", "switchboard"],
            system=None,
            location_type=None,
            check_subject="nameplate",
        )
        assert left == right

    def test_different_subjects_do_not_group(self) -> None:
        nameplate = compute_check_key(
            equipment_class=["switchboard"],
            system=None,
            location_type=None,
            check_subject="equipment nameplate",
        )
        label = compute_check_key(
            equipment_class=["switchboard"],
            system=None,
            location_type=None,
            check_subject="arc flash warning label",
        )
        assert nameplate != label

    def test_a_wildcard_system_does_not_group_with_a_specific_one(self) -> None:
        """A requirement that applies everywhere is not the same check as one
        that applies only to normal power."""
        everywhere = compute_check_key(
            equipment_class=["switchboard"],
            system=None,
            location_type=None,
            check_subject="nameplate",
        )
        specific = compute_check_key(
            equipment_class=["switchboard"],
            system="normal_power",
            location_type=None,
            check_subject="nameplate",
        )
        assert everywhere != specific

    def test_a_reworded_subject_is_missed_rather_than_guessed_at(self) -> None:
        """Documented limitation: this is the direction the rule fails in."""
        short = compute_check_key(
            equipment_class=["switchboard"],
            system=None,
            location_type=None,
            check_subject="arc flash label",
        )
        long = compute_check_key(
            equipment_class=["switchboard"],
            system=None,
            location_type=None,
            check_subject="arc flash warning label",
        )
        assert short != long, "a curator edits check_key to group these by hand"


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def rule_set(db: Session, project: Project) -> RuleSet:
    return f.make_rule_set(db, project, "1.0.0")


@pytest.fixture
def curator(db: Session) -> AppUser:
    return f.make_user(db, UserRole.CURATOR)


def a_document(db: Session, project: Project, doc_type: DocumentType) -> SourceDocument:
    document = f.make_document(db, project)
    document.doc_type = doc_type
    db.flush()
    return document


def a_requirement(
    db: Session,
    project: Project,
    rule_set: RuleSet,
    document: SourceDocument,
    *,
    subject: str = "equipment nameplate",
    criticality: Criticality = Criticality.QUALITY,
    status: RequirementStatus = RequirementStatus.APPROVED,
) -> Requirement:
    requirement = f.make_requirement(
        db,
        project,
        document,
        rule_set=rule_set,
        criticality=criticality,
        status=status,
        why_it_matters="Somebody opening this board needs to know what is inside it.",
    )
    requirement.check_key = compute_check_key(
        equipment_class=["switchboard"],
        system=None,
        location_type=None,
        check_subject=subject,
    )
    db.flush()
    return requirement


class TestRankingContestedGroups:
    def test_a_spec_outranks_a_submittal_on_the_same_check(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        spec_doc = a_document(db, project, DocumentType.SPEC_SECTION)
        submittal_doc = a_document(db, project, DocumentType.APPROVED_SUBMITTAL)
        spec = a_requirement(db, project, rule_set, spec_doc)
        submittal = a_requirement(db, project, rule_set, submittal_doc)

        report = resolve_precedence(db, rule_set.id)

        assert report.contested == 1
        assert report.resolved == 1
        assert spec.precedence_rank < submittal.precedence_rank

    def test_requirements_on_different_checks_are_not_contested(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        spec_doc = a_document(db, project, DocumentType.SPEC_SECTION)
        submittal_doc = a_document(db, project, DocumentType.APPROVED_SUBMITTAL)
        a_requirement(db, project, rule_set, spec_doc, subject="equipment nameplate")
        a_requirement(db, project, rule_set, submittal_doc, subject="arc flash label")

        report = resolve_precedence(db, rule_set.id)

        assert report.groups == 2
        assert report.contested == 0

    def test_two_requirements_from_one_document_are_not_contested(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        """One document saying a thing twice is a duplicate, not a conflict."""
        spec_doc = a_document(db, project, DocumentType.SPEC_SECTION)
        a_requirement(db, project, rule_set, spec_doc)
        a_requirement(db, project, rule_set, spec_doc)

        assert resolve_precedence(db, rule_set.id).contested == 0

    def test_a_retired_requirement_is_out_of_the_running(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        spec_doc = a_document(db, project, DocumentType.SPEC_SECTION)
        submittal_doc = a_document(db, project, DocumentType.APPROVED_SUBMITTAL)
        a_requirement(db, project, rule_set, spec_doc)
        a_requirement(db, project, rule_set, submittal_doc, status=RequirementStatus.RETIRED)

        assert resolve_precedence(db, rule_set.id).contested == 0


class TestConflictsSurface:
    def test_a_safety_disagreement_opens_a_conflict(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        spec_doc = a_document(db, project, DocumentType.SPEC_SECTION)
        submittal_doc = a_document(db, project, DocumentType.APPROVED_SUBMITTAL)
        a_requirement(db, project, rule_set, spec_doc, criticality=Criticality.SAFETY)
        a_requirement(db, project, rule_set, submittal_doc)

        report = resolve_precedence(db, rule_set.id)

        assert report.conflicts_opened == 1
        conflicts = open_conflicts(db, rule_set.id)
        assert "safety" in conflicts[0].reason.lower()

    def test_the_conflict_shows_what_the_rules_saw(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        a_requirement(db, project, rule_set, first)
        a_requirement(db, project, rule_set, second)

        resolve_precedence(db, rule_set.id)

        conflict = open_conflicts(db, rule_set.id)[0]
        assert len(conflict.candidates) == 2
        assert {c["doc_type"] for c in conflict.candidates} == {"spec_section"}
        assert all(c["statement"] for c in conflict.candidates)

    def test_re_running_updates_the_conflict_rather_than_duplicating_it(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        """The second document arrives later; this runs again when it does."""
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        a_requirement(db, project, rule_set, first)
        a_requirement(db, project, rule_set, second)

        resolve_precedence(db, rule_set.id)
        second_run = resolve_precedence(db, rule_set.id)

        assert second_run.conflicts_opened == 0
        assert len(open_conflicts(db, rule_set.id)) == 1
        assert db.query(RequirementConflict).count() == 1

    def test_a_conflict_that_no_longer_holds_is_dismissed(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        a_requirement(db, project, rule_set, first)
        loser = a_requirement(db, project, rule_set, second)
        resolve_precedence(db, rule_set.id)

        loser.status = RequirementStatus.RETIRED
        db.flush()
        report = resolve_precedence(db, rule_set.id)

        assert report.conflicts_dismissed == 1
        assert open_conflicts(db, rule_set.id) == []


class TestAPersonResolvingAConflict:
    def test_the_winner_stands_and_the_losers_are_retired(
        self, db: Session, project: Project, rule_set: RuleSet, curator: AppUser
    ) -> None:
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        winner = a_requirement(db, project, rule_set, first)
        loser = a_requirement(db, project, rule_set, second)
        resolve_precedence(db, rule_set.id)
        conflict = open_conflicts(db, rule_set.id)[0]

        resolved = resolve_conflict(
            db,
            conflict.id,
            winner_requirement_id=winner.id,
            resolved_by=curator.id,
            note="The spec governs; the submittal was not approved as a deviation.",
        )

        assert resolved.status is ConflictStatus.RESOLVED
        assert resolved.resolved_by == curator.id
        assert loser.status is RequirementStatus.RETIRED
        assert winner.status is RequirementStatus.APPROVED
        assert winner.precedence_rank == 0

    def test_a_retired_loser_is_kept_rather_than_deleted(
        self, db: Session, project: Project, rule_set: RuleSet, curator: AppUser
    ) -> None:
        """Which document lost, and who decided, is the answer to a later question."""
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        winner = a_requirement(db, project, rule_set, first)
        loser = a_requirement(db, project, rule_set, second)
        resolve_precedence(db, rule_set.id)
        conflict = open_conflicts(db, rule_set.id)[0]

        resolve_conflict(db, conflict.id, winner_requirement_id=winner.id, resolved_by=curator.id)

        assert db.get(Requirement, (loser.id, rule_set.version)) is not None

    def test_a_winner_outside_the_conflict_is_refused(
        self, db: Session, project: Project, rule_set: RuleSet, curator: AppUser
    ) -> None:
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        a_requirement(db, project, rule_set, first)
        a_requirement(db, project, rule_set, second)
        resolve_precedence(db, rule_set.id)
        conflict = open_conflicts(db, rule_set.id)[0]

        with pytest.raises(GroupingError, match="not one of"):
            resolve_conflict(
                db, conflict.id, winner_requirement_id=uuid.uuid4(), resolved_by=curator.id
            )

    def test_resolving_twice_is_refused(
        self, db: Session, project: Project, rule_set: RuleSet, curator: AppUser
    ) -> None:
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        winner = a_requirement(db, project, rule_set, first)
        a_requirement(db, project, rule_set, second)
        resolve_precedence(db, rule_set.id)
        conflict = open_conflicts(db, rule_set.id)[0]

        resolve_conflict(db, conflict.id, winner_requirement_id=winner.id, resolved_by=curator.id)
        with pytest.raises(GroupingError, match="already resolved"):
            resolve_conflict(
                db, conflict.id, winner_requirement_id=winner.id, resolved_by=curator.id
            )


class TestPublishingWithAConflictOpen:
    def test_an_open_conflict_blocks_publication(
        self, db: Session, project: Project, rule_set: RuleSet, curator: AppUser
    ) -> None:
        """A rule set with a known contradiction should not be telling anyone what to check."""
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        a_requirement(db, project, rule_set, first)
        a_requirement(db, project, rule_set, second)
        resolve_precedence(db, rule_set.id)

        with pytest.raises(curation.PublishRefusedError) as raised:
            curation.publish(db, rule_set.id, published_by=curator.id)

        assert any("precedence conflict" in r for r in raised.value.reasons)

    def test_resolving_the_conflict_unblocks_publication(
        self, db: Session, project: Project, rule_set: RuleSet, curator: AppUser
    ) -> None:
        first = a_document(db, project, DocumentType.SPEC_SECTION)
        second = a_document(db, project, DocumentType.SPEC_SECTION)
        winner = a_requirement(db, project, rule_set, first)
        a_requirement(db, project, rule_set, second)
        resolve_precedence(db, rule_set.id)
        conflict = open_conflicts(db, rule_set.id)[0]
        resolve_conflict(db, conflict.id, winner_requirement_id=winner.id, resolved_by=curator.id)

        summary = curation.publish(db, rule_set.id, published_by=curator.id)

        assert summary.approved == 1
