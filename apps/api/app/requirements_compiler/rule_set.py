"""Rule set curation and versioning.

Publishing is the moment a rule set starts telling techs what to check, so it is
the moment the safety rule bites: a set containing an unapproved `safety`
requirement cannot be published, whatever else is true of it.

A spec revision produces a new version and a diff. Requirement identity is
(id, ruleset_version), so a requirement carried forward unchanged keeps its id
and the diff can tell "unchanged" from "replaced".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import AppUser, Requirement, RuleSet, RuleSetStatus
from app.models.enums import Criticality, RequirementStatus, UserRole
from app.requirements_compiler.grouping import open_conflicts

log = get_logger(__name__)

#: Roles allowed to approve a requirement into a rule set.
CURATOR_ROLES = frozenset({UserRole.CURATOR, UserRole.ADMIN})

#: Fields a diff compares. Bookkeeping columns are deliberately absent: a
#: requirement whose `updated_at` moved has not changed in any way a tech
#: would notice.
COMPARED_FIELDS = (
    "statement",
    "verification_method",
    "criticality",
    "pass_criteria",
    "evidence_spec",
    "why_it_matters",
    "applies_to_equipment_class",
    "applies_to_system",
    "applies_to_location_type",
    "source_doc_id",
    "source_clause",
    "source_page",
    "precedence_rank",
)


class CurationError(RuntimeError):
    """A curation action that must not be performed."""


class PublishRefusedError(CurationError):
    """The rule set is not fit to go live. `reasons` says why, in plain words."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class PublishSummary:
    rule_set_id: uuid.UUID
    version: str
    approved: int
    left_behind: int
    """Draft or needs_review requirements that will not generate checklist items."""


@dataclass(frozen=True)
class FieldChange:
    field: str
    before: Any
    after: Any


@dataclass(frozen=True)
class RequirementChange:
    requirement_id: uuid.UUID
    changes: tuple[FieldChange, ...]


@dataclass(frozen=True)
class RuleSetDiff:
    base_version: str
    head_version: str
    added: tuple[uuid.UUID, ...] = ()
    removed: tuple[uuid.UUID, ...] = ()
    changed: tuple[RequirementChange, ...] = ()
    unchanged: int = 0
    _: tuple[()] = field(default=(), repr=False)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def create_draft(
    session: Session,
    project_id: uuid.UUID,
    version: str,
    *,
    supersedes_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> RuleSet:
    existing = session.execute(
        select(RuleSet).where(RuleSet.project_id == project_id, RuleSet.version == version)
    ).scalar_one_or_none()
    if existing is not None:
        raise CurationError(f"Rule set version {version} already exists for this project.")

    rule_set = RuleSet(
        project_id=project_id,
        version=version,
        status=RuleSetStatus.DRAFT,
        supersedes_id=supersedes_id,
        notes=notes,
    )
    session.add(rule_set)
    session.flush()
    return rule_set


def _require_curator(session: Session, user_id: uuid.UUID) -> AppUser:
    user = session.get(AppUser, user_id)
    if user is None:
        raise CurationError("No such user.")
    if not user.is_active:
        raise CurationError(f"{user.display_name} is not an active user.")
    if not (set(user.roles) & CURATOR_ROLES):
        raise CurationError(
            f"{user.display_name} is not a curator and cannot approve requirements."
        )
    return user


def approve_requirement(
    session: Session,
    requirement_id: uuid.UUID,
    ruleset_version: str,
    *,
    approved_by: uuid.UUID,
) -> Requirement:
    """Approve one requirement into its rule set.

    Refuses on a published rule set: a published set is what the field is
    walking, and changing it underneath them is the silent overwrite the
    architecture doc rules out.
    """
    curator = _require_curator(session, approved_by)
    requirement = session.get(Requirement, (requirement_id, ruleset_version))
    if requirement is None:
        raise CurationError(f"No requirement {requirement_id} at version {ruleset_version}.")

    rule_set = session.get(RuleSet, requirement.rule_set_id)
    if rule_set is not None and rule_set.status is not RuleSetStatus.DRAFT:
        raise CurationError(
            f"Rule set {rule_set.version} is {rule_set.status.value}; "
            "approve into a new draft version instead."
        )

    requirement.status = RequirementStatus.APPROVED
    requirement.approved_by = curator.id
    requirement.approved_at = datetime.now(UTC)
    session.flush()

    log.info(
        "curation.requirement_approved",
        requirement_id=str(requirement_id),
        ruleset_version=ruleset_version,
        criticality=requirement.criticality.value,
        approved_by=str(curator.id),
    )
    return requirement


def reject_requirement(
    session: Session,
    requirement_id: uuid.UUID,
    ruleset_version: str,
    *,
    rejected_by: uuid.UUID,
) -> Requirement:
    """Retire a requirement rather than deleting it.

    The extraction that produced it stays visible: a rejected requirement is
    evidence about the extraction prompt, and deleting it loses that.
    """
    _require_curator(session, rejected_by)
    requirement = session.get(Requirement, (requirement_id, ruleset_version))
    if requirement is None:
        raise CurationError(f"No requirement {requirement_id} at version {ruleset_version}.")

    requirement.status = RequirementStatus.RETIRED
    requirement.approved_by = None
    requirement.approved_at = None
    session.flush()
    return requirement


def _requirements_in(session: Session, rule_set_id: uuid.UUID) -> list[Requirement]:
    return list(
        session.execute(select(Requirement).where(Requirement.rule_set_id == rule_set_id))
        .scalars()
        .all()
    )


def publish(session: Session, rule_set_id: uuid.UUID, *, published_by: uuid.UUID) -> PublishSummary:
    """Put a rule set live, or refuse and say why."""
    curator = _require_curator(session, published_by)
    rule_set = session.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise CurationError(f"No rule set {rule_set_id}.")

    reasons: list[str] = []
    if rule_set.status is not RuleSetStatus.DRAFT:
        reasons.append(f"This rule set is already {rule_set.status.value}.")

    requirements = _requirements_in(session, rule_set_id)
    approved = [r for r in requirements if r.status is RequirementStatus.APPROVED]
    left_behind = [
        r
        for r in requirements
        if r.status in (RequirementStatus.DRAFT, RequirementStatus.NEEDS_REVIEW)
    ]

    # The non-negotiable rule, applied at the moment a rule set starts telling
    # techs what to check.
    unapproved_safety = [
        r
        for r in requirements
        if r.criticality is Criticality.SAFETY
        and r.status is not RequirementStatus.APPROVED
        and r.status is not RequirementStatus.RETIRED
    ]
    if unapproved_safety:
        reasons.append(
            f"{len(unapproved_safety)} safety requirement(s) have not been approved by a "
            "qualified person. Safety requirements never go live unapproved."
        )

    if not approved:
        reasons.append("Nothing in this rule set is approved, so there is nothing to publish.")

    # A rule set with a known contradiction in it should not be telling anyone
    # what to check. The conflict says two documents disagree; publishing anyway
    # means the field silently gets one of them, or both.
    unresolved = open_conflicts(session, rule_set_id)
    if unresolved:
        reasons.append(
            f"{len(unresolved)} precedence conflict(s) are unresolved. Two documents govern "
            "the same check and a person has to choose which one stands."
        )

    if reasons:
        log.warning(
            "curation.publish_refused",
            rule_set_id=str(rule_set_id),
            version=rule_set.version,
            reasons=reasons,
        )
        raise PublishRefusedError(reasons)

    rule_set.status = RuleSetStatus.PUBLISHED
    rule_set.published_by = curator.id
    rule_set.published_at = datetime.now(UTC)

    if rule_set.supersedes_id is not None:
        previous = session.get(RuleSet, rule_set.supersedes_id)
        if previous is not None and previous.status is RuleSetStatus.PUBLISHED:
            previous.status = RuleSetStatus.SUPERSEDED

    session.flush()
    log.info(
        "curation.published",
        rule_set_id=str(rule_set_id),
        version=rule_set.version,
        approved=len(approved),
        left_behind=len(left_behind),
        published_by=str(curator.id),
    )
    return PublishSummary(
        rule_set_id=rule_set_id,
        version=rule_set.version,
        approved=len(approved),
        left_behind=len(left_behind),
    )


def diff(session: Session, base_id: uuid.UUID, head_id: uuid.UUID) -> RuleSetDiff:
    """What changed between two rule set versions.

    Only approved requirements are compared: drafts never reached the field, so
    they are not part of what changed for anyone walking the building.
    """
    base = session.get(RuleSet, base_id)
    head = session.get(RuleSet, head_id)
    if base is None or head is None:
        raise CurationError("Both rule sets must exist to diff them.")

    def approved_by_id(rule_set_id: uuid.UUID) -> dict[uuid.UUID, Requirement]:
        return {
            r.id: r
            for r in _requirements_in(session, rule_set_id)
            if r.status is RequirementStatus.APPROVED
        }

    before, after = approved_by_id(base_id), approved_by_id(head_id)

    added = tuple(sorted(set(after) - set(before), key=str))
    removed = tuple(sorted(set(before) - set(after), key=str))

    changed: list[RequirementChange] = []
    unchanged = 0
    for requirement_id in sorted(set(before) & set(after), key=str):
        field_changes = tuple(
            FieldChange(
                field=name,
                before=getattr(before[requirement_id], name),
                after=getattr(after[requirement_id], name),
            )
            for name in COMPARED_FIELDS
            if getattr(before[requirement_id], name) != getattr(after[requirement_id], name)
        )
        if field_changes:
            changed.append(RequirementChange(requirement_id=requirement_id, changes=field_changes))
        else:
            unchanged += 1

    return RuleSetDiff(
        base_version=base.version,
        head_version=head.version,
        added=added,
        removed=removed,
        changed=tuple(changed),
        unchanged=unchanged,
    )
