"""Deterministic precedence resolution.

From the architecture doc: "Contract documents over approved submittal over
manufacturer IOM, except where a submittal was approved as a deviation, which
wins for that item. RFI responses supersede whatever they answer. Conflicts that
the rules cannot settle are surfaced, not resolved."

The last clause is the important one. This module's job is as much to *refuse*
to resolve as to resolve: a rule set that quietly picked a winner between two
contradictory documents would send a tech to check the wrong thing, and nobody
would know until the rework.

Pure functions, no database, no model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.models.enums import Criticality, DocumentType

#: Lower wins. Standards are ranked last and flagged; see `STANDARD_IS_UNRANKED`.
BASE_RANK: dict[DocumentType, int] = {
    DocumentType.RFI_RESPONSE: 0,
    DocumentType.SPEC_SECTION: 1,
    DocumentType.APPROVED_SUBMITTAL: 2,
    DocumentType.MANUFACTURER_IOM: 3,
    DocumentType.STANDARD: 4,
}

#: The architecture doc ranks contract documents, submittals and IOMs, and says
#: RFI responses supersede what they answer. It does not say where a referenced
#: standard sits. Ranking it last is the conservative reading — a standard is
#: usually incorporated *by* the contract rather than overriding it — but a
#: standard losing to another document is surfaced rather than silently applied.
#: Recorded as Q13 in docs/OPEN_QUESTIONS.md.
STANDARD_IS_UNRANKED = True


class Resolution(StrEnum):
    RESOLVED = "resolved"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class Candidate:
    """One requirement competing to govern the same check on the same equipment."""

    requirement_id: uuid.UUID
    document_id: uuid.UUID
    doc_type: DocumentType
    criticality: Criticality
    statement: str = ""
    #: A submittal approved as a deviation wins for its item, over the contract.
    approved_as_deviation: bool = False
    #: For an RFI response: the documents whose text it answers.
    supersedes_document_ids: frozenset[uuid.UUID] = frozenset()


@dataclass(frozen=True)
class Ranked:
    candidate: Candidate
    precedence_rank: int
    superseded_by: uuid.UUID | None = None


@dataclass(frozen=True)
class PrecedenceOutcome:
    resolution: Resolution
    ranked: tuple[Ranked, ...]
    winner: Candidate | None = None
    conflict_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.resolution is Resolution.RESOLVED


def _superseded_ids(candidates: list[Candidate]) -> dict[uuid.UUID, uuid.UUID]:
    """Map document id -> the RFI response document that answers it."""
    superseded: dict[uuid.UUID, uuid.UUID] = {}
    for candidate in candidates:
        if candidate.doc_type is not DocumentType.RFI_RESPONSE:
            continue
        for document_id in candidate.supersedes_document_ids:
            superseded[document_id] = candidate.document_id
    return superseded


def resolve(candidates: list[Candidate]) -> PrecedenceOutcome:
    """Rank a group of competing requirements, or refuse to.

    The group is expected to be requirements that govern the same check on the
    same equipment; grouping is the caller's job, because it depends on how the
    rule set is being compiled.
    """
    if not candidates:
        return PrecedenceOutcome(
            resolution=Resolution.CONFLICT,
            ranked=(),
            conflict_reason="No candidates were given.",
        )

    superseded = _superseded_ids(candidates)

    ranked = tuple(
        sorted(
            (
                Ranked(
                    candidate=candidate,
                    precedence_rank=BASE_RANK[candidate.doc_type],
                    superseded_by=superseded.get(candidate.document_id),
                )
                for candidate in candidates
            ),
            key=lambda r: (r.superseded_by is not None, r.precedence_rank),
        )
    )

    live = [r for r in ranked if r.superseded_by is None]
    if not live:
        return PrecedenceOutcome(
            resolution=Resolution.CONFLICT,
            ranked=ranked,
            conflict_reason=(
                "Every candidate was superseded by an RFI response that is not itself "
                "in this group."
            ),
        )

    if len(live) == 1:
        return PrecedenceOutcome(
            resolution=Resolution.RESOLVED, ranked=ranked, winner=live[0].candidate
        )

    # A safety requirement is never resolved away by a rule. Whatever the
    # document hierarchy says, a person decides which safety requirement stands.
    safety = [r for r in live if r.candidate.criticality is Criticality.SAFETY]
    if safety:
        return PrecedenceOutcome(
            resolution=Resolution.CONFLICT,
            ranked=ranked,
            conflict_reason=(
                "More than one document governs this check and at least one is a safety "
                "requirement. Safety conflicts are always settled by a qualified person."
            ),
        )

    deviations = [r for r in live if r.candidate.approved_as_deviation]
    if len(deviations) == 1:
        return PrecedenceOutcome(
            resolution=Resolution.RESOLVED, ranked=ranked, winner=deviations[0].candidate
        )
    if len(deviations) > 1:
        return PrecedenceOutcome(
            resolution=Resolution.CONFLICT,
            ranked=ranked,
            conflict_reason=(
                f"{len(deviations)} submittals are approved as deviations for the same item. "
                "Only one can govern."
            ),
        )

    best_rank = live[0].precedence_rank
    tied = [r for r in live if r.precedence_rank == best_rank]
    if len(tied) > 1:
        distinct_documents = {r.candidate.document_id for r in tied}
        if len(distinct_documents) > 1:
            return PrecedenceOutcome(
                resolution=Resolution.CONFLICT,
                ranked=ranked,
                conflict_reason=(
                    f"{len(tied)} documents of the same type "
                    f"({tied[0].candidate.doc_type.value}) govern this check and the rules "
                    "cannot rank them against each other."
                ),
            )

    if STANDARD_IS_UNRANKED and live[0].candidate.doc_type is not DocumentType.STANDARD:
        losing_standards = [r for r in live[1:] if r.candidate.doc_type is DocumentType.STANDARD]
        if losing_standards:
            return PrecedenceOutcome(
                resolution=Resolution.CONFLICT,
                ranked=ranked,
                conflict_reason=(
                    "A referenced standard disagrees with another document. The architecture "
                    "doc does not rank standards, so a person decides. See OPEN_QUESTIONS Q13."
                ),
            )

    return PrecedenceOutcome(
        resolution=Resolution.RESOLVED, ranked=ranked, winner=live[0].candidate
    )
