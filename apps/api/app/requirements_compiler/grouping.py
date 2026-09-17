"""Deciding which requirements govern the same check, then ranking them.

The precedence resolver ranks a group. This module decides what a group *is*,
which turned out to be the harder half of the problem (OPEN_QUESTIONS Q17).

The rule here is deliberately literal: two requirements are the same check when
they govern the same equipment and the model named the same subject for both.
It will miss pairs that word the subject differently — "arc flash label" against
"arc flash warning label" — and that is the intended direction to fail in. A
missed group produces two checklist items, which a tech notices and a reviewer
can clear. A wrong group silently discards one document's requirement, and
nobody finds out until the rework.

For the pairs it misses, a curator can edit `check_key` so two requirements
group by hand. That is the escape hatch, and it is cheaper than a grouping rule
clever enough to be wrong.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import (
    AppUser,
    ConflictStatus,
    Requirement,
    RequirementConflict,
    RuleSet,
    SourceDocument,
)
from app.models.enums import RequirementStatus
from app.requirements_compiler.precedence import Candidate, resolve

log = get_logger(__name__)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class GroupingError(RuntimeError):
    """A grouping or resolution action that cannot be performed."""


def normalize_subject(subject: str) -> str:
    """Punctuation- and space-insensitive form of a check subject.

    Collapsing spaces means "nameplate" and "name plate" group, which is a
    common enough disagreement between documents to be worth catching. It does
    not attempt synonyms or stemming: that is where a grouping rule starts being
    wrong in ways nobody can see.
    """
    return _NON_ALNUM.sub("", subject.strip().lower())


def compute_check_key(
    *,
    equipment_class: list[str],
    system: str | None,
    location_type: str | None,
    check_subject: str,
) -> str:
    """A stable key for "this check, on this equipment".

    Equipment classes are sorted so two documents listing them in a different
    order still match. A missing system or location type is a wildcard in the
    requirement and a literal here, so a requirement that applies everywhere does
    not silently group with one that applies in electrical rooms only.
    """
    classes = ",".join(sorted(normalize_subject(c) for c in equipment_class))
    return "|".join(
        [
            classes,
            normalize_subject(system) if system else "*",
            normalize_subject(location_type) if location_type else "*",
            normalize_subject(check_subject),
        ]
    )


@dataclass(frozen=True)
class PrecedenceReport:
    rule_set_id: uuid.UUID
    groups: int = 0
    contested: int = 0
    """Groups where more than one document governs the same check."""
    resolved: int = 0
    conflicts_opened: int = 0
    conflicts_dismissed: int = 0


def _candidate_of(requirement: Requirement, document: SourceDocument) -> Candidate:
    return Candidate(
        requirement_id=requirement.id,
        document_id=document.id,
        doc_type=document.doc_type,
        criticality=requirement.criticality,
        statement=requirement.statement,
        # Deviation approval and RFI targets are properties of the document, and
        # nothing records them yet — see the note in resolve_precedence.
        approved_as_deviation=False,
        supersedes_document_ids=frozenset(),
    )


def resolve_precedence(session: Session, rule_set_id: uuid.UUID) -> PrecedenceReport:
    """Group the rule set's requirements by check and rank each group.

    Safe to re-run: a conflict that no longer holds is dismissed, and a
    still-live conflict is updated in place rather than duplicated. That matters
    because the second document arrives later — a spec compiles on Monday and
    its submittal on Thursday, and the conflict only exists after both.
    """
    rule_set = session.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise GroupingError(f"No rule set {rule_set_id}.")

    requirements = [
        r
        for r in session.execute(select(Requirement).where(Requirement.rule_set_id == rule_set_id))
        .scalars()
        .all()
        if r.status is not RequirementStatus.RETIRED
    ]

    documents = {
        d.id: d
        for d in session.execute(
            select(SourceDocument).where(
                SourceDocument.id.in_({r.source_doc_id for r in requirements})
            )
        )
        .scalars()
        .all()
    }

    groups: dict[str, list[Requirement]] = {}
    for requirement in requirements:
        key = requirement.check_key or f"ungrouped:{requirement.id}"
        groups.setdefault(key, []).append(requirement)

    open_conflicts = {
        c.check_key: c
        for c in session.execute(
            select(RequirementConflict).where(
                RequirementConflict.rule_set_id == rule_set_id,
                RequirementConflict.status == ConflictStatus.OPEN,
            )
        )
        .scalars()
        .all()
    }

    report = PrecedenceReport(rule_set_id=rule_set_id, groups=len(groups))
    contested = resolved_count = opened = 0
    still_conflicting: set[str] = set()

    for check_key, members in groups.items():
        distinct_documents = {r.source_doc_id for r in members}
        if len(distinct_documents) < 2:
            # Nothing competing. Rank within the group is meaningless, so it is
            # left at whatever compilation set from the document type.
            continue

        contested += 1
        candidates = [_candidate_of(r, documents[r.source_doc_id]) for r in members]
        outcome = resolve(candidates)

        candidate_json = [
            {
                "requirement_id": str(ranked.candidate.requirement_id),
                "document_id": str(ranked.candidate.document_id),
                "doc_type": ranked.candidate.doc_type.value,
                "precedence_rank": ranked.precedence_rank,
                "superseded_by": str(ranked.superseded_by) if ranked.superseded_by else None,
                "statement": ranked.candidate.statement,
            }
            for ranked in outcome.ranked
        ]

        if outcome.resolved:
            resolved_count += 1
            by_id = {r.id: r for r in members}
            for position, ranked in enumerate(outcome.ranked):
                member = by_id.get(ranked.candidate.requirement_id)
                if member is not None:
                    member.precedence_rank = position
            continue

        still_conflicting.add(check_key)
        existing = open_conflicts.get(check_key)
        if existing is not None:
            existing.reason = outcome.conflict_reason or "The rules could not choose."
            existing.candidates = candidate_json
        else:
            opened += 1
            session.add(
                RequirementConflict(
                    rule_set_id=rule_set_id,
                    check_key=check_key,
                    reason=outcome.conflict_reason or "The rules could not choose.",
                    candidates=candidate_json,
                    status=ConflictStatus.OPEN,
                )
            )

    dismissed = 0
    for check_key, conflict in open_conflicts.items():
        if check_key not in still_conflicting:
            conflict.status = ConflictStatus.DISMISSED
            dismissed += 1

    session.flush()

    report = PrecedenceReport(
        rule_set_id=rule_set_id,
        groups=len(groups),
        contested=contested,
        resolved=resolved_count,
        conflicts_opened=opened,
        conflicts_dismissed=dismissed,
    )
    log.info(
        "precedence.resolved",
        rule_set_id=str(rule_set_id),
        groups=report.groups,
        contested=report.contested,
        resolved=report.resolved,
        conflicts_opened=report.conflicts_opened,
        conflicts_dismissed=report.conflicts_dismissed,
    )
    return report


def open_conflicts(session: Session, rule_set_id: uuid.UUID) -> list[RequirementConflict]:
    return list(
        session.execute(
            select(RequirementConflict).where(
                RequirementConflict.rule_set_id == rule_set_id,
                RequirementConflict.status == ConflictStatus.OPEN,
            )
        )
        .scalars()
        .all()
    )


def resolve_conflict(
    session: Session,
    conflict_id: uuid.UUID,
    *,
    winner_requirement_id: uuid.UUID,
    resolved_by: uuid.UUID,
    note: str | None = None,
) -> RequirementConflict:
    """A person picks which requirement governs. The losers are retired.

    Retired rather than deleted: which document lost, and who decided, is the
    answer when somebody later asks why the submittal's version is not being
    checked.
    """
    conflict = session.get(RequirementConflict, conflict_id)
    if conflict is None:
        raise GroupingError(f"No conflict {conflict_id}.")
    if conflict.status is not ConflictStatus.OPEN:
        raise GroupingError(f"That conflict is already {conflict.status.value}.")

    user = session.get(AppUser, resolved_by)
    if user is None or not user.is_active:
        raise GroupingError("No such active user.")

    contested_ids = {uuid.UUID(c["requirement_id"]) for c in conflict.candidates}
    if winner_requirement_id not in contested_ids:
        raise GroupingError("The chosen requirement is not one of the ones in conflict.")

    rule_set = session.get(RuleSet, conflict.rule_set_id)
    version = rule_set.version if rule_set is not None else None

    for requirement_id in contested_ids - {winner_requirement_id}:
        loser = session.get(Requirement, (requirement_id, version))
        if loser is not None:
            loser.status = RequirementStatus.RETIRED
            loser.approved_by = None
            loser.approved_at = None

    winner = session.get(Requirement, (winner_requirement_id, version))
    if winner is not None:
        winner.precedence_rank = 0

    conflict.status = ConflictStatus.RESOLVED
    conflict.winner_requirement_id = winner_requirement_id
    conflict.resolution_note = note
    conflict.resolved_by = resolved_by
    conflict.resolved_at = datetime.now(UTC)
    session.flush()

    log.info(
        "precedence.conflict_resolved",
        conflict_id=str(conflict_id),
        winner_requirement_id=str(winner_requirement_id),
        retired=len(contested_ids) - 1,
        resolved_by=str(resolved_by),
    )
    return conflict
