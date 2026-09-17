"""Precedence resolution.

Half of these assert that the resolver *refuses*. A rule set that quietly picks
a winner between contradictory documents sends a tech to check the wrong thing,
and nobody finds out until the rework.
"""

from __future__ import annotations

import uuid

from app.models.enums import Criticality, DocumentType
from app.requirements_compiler.precedence import (
    Candidate,
    Resolution,
    resolve,
)

SPEC_DOC = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
SUBMITTAL_DOC = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000002")
IOM_DOC = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000003")
RFI_DOC = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000004")
STANDARD_DOC = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000005")
OTHER_SPEC_DOC = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000006")


def candidate(
    doc_type: DocumentType,
    document_id: uuid.UUID,
    *,
    criticality: Criticality = Criticality.QUALITY,
    approved_as_deviation: bool = False,
    supersedes: frozenset[uuid.UUID] = frozenset(),
) -> Candidate:
    return Candidate(
        requirement_id=uuid.uuid4(),
        document_id=document_id,
        doc_type=doc_type,
        criticality=criticality,
        approved_as_deviation=approved_as_deviation,
        supersedes_document_ids=supersedes,
    )


class TestTheDocumentHierarchy:
    def test_contract_beats_approved_submittal(self) -> None:
        spec = candidate(DocumentType.SPEC_SECTION, SPEC_DOC)
        submittal = candidate(DocumentType.APPROVED_SUBMITTAL, SUBMITTAL_DOC)

        outcome = resolve([submittal, spec])

        assert outcome.resolved
        assert outcome.winner == spec

    def test_approved_submittal_beats_manufacturer_iom(self) -> None:
        submittal = candidate(DocumentType.APPROVED_SUBMITTAL, SUBMITTAL_DOC)
        iom = candidate(DocumentType.MANUFACTURER_IOM, IOM_DOC)

        outcome = resolve([iom, submittal])

        assert outcome.resolved
        assert outcome.winner == submittal

    def test_a_single_candidate_wins_uncontested(self) -> None:
        iom = candidate(DocumentType.MANUFACTURER_IOM, IOM_DOC)
        outcome = resolve([iom])
        assert outcome.resolved
        assert outcome.winner == iom

    def test_every_candidate_is_ranked_even_the_losers(self) -> None:
        """The reviewer needs to see what lost, not just what won."""
        outcome = resolve(
            [
                candidate(DocumentType.MANUFACTURER_IOM, IOM_DOC),
                candidate(DocumentType.SPEC_SECTION, SPEC_DOC),
                candidate(DocumentType.APPROVED_SUBMITTAL, SUBMITTAL_DOC),
            ]
        )
        assert [r.candidate.doc_type for r in outcome.ranked] == [
            DocumentType.SPEC_SECTION,
            DocumentType.APPROVED_SUBMITTAL,
            DocumentType.MANUFACTURER_IOM,
        ]


class TestApprovedDeviations:
    def test_a_submittal_approved_as_a_deviation_beats_the_contract(self) -> None:
        """The one documented inversion of the hierarchy."""
        spec = candidate(DocumentType.SPEC_SECTION, SPEC_DOC)
        deviation = candidate(
            DocumentType.APPROVED_SUBMITTAL, SUBMITTAL_DOC, approved_as_deviation=True
        )

        outcome = resolve([spec, deviation])

        assert outcome.resolved
        assert outcome.winner == deviation

    def test_two_deviations_for_the_same_item_are_not_resolved(self) -> None:
        outcome = resolve(
            [
                candidate(
                    DocumentType.APPROVED_SUBMITTAL, SUBMITTAL_DOC, approved_as_deviation=True
                ),
                candidate(DocumentType.APPROVED_SUBMITTAL, IOM_DOC, approved_as_deviation=True),
            ]
        )

        assert outcome.resolution is Resolution.CONFLICT
        assert outcome.winner is None
        assert "deviations" in (outcome.conflict_reason or "")

    def test_a_deviation_does_not_win_over_an_rfi_that_answers_it(self) -> None:
        deviation = candidate(
            DocumentType.APPROVED_SUBMITTAL, SUBMITTAL_DOC, approved_as_deviation=True
        )
        rfi = candidate(DocumentType.RFI_RESPONSE, RFI_DOC, supersedes=frozenset({SUBMITTAL_DOC}))

        outcome = resolve([deviation, rfi])

        assert outcome.resolved
        assert outcome.winner == rfi


class TestRfiResponses:
    def test_an_rfi_response_supersedes_what_it_answers(self) -> None:
        spec = candidate(DocumentType.SPEC_SECTION, SPEC_DOC)
        rfi = candidate(DocumentType.RFI_RESPONSE, RFI_DOC, supersedes=frozenset({SPEC_DOC}))

        outcome = resolve([spec, rfi])

        assert outcome.resolved
        assert outcome.winner == rfi

    def test_the_superseded_candidate_records_what_superseded_it(self) -> None:
        spec = candidate(DocumentType.SPEC_SECTION, SPEC_DOC)
        rfi = candidate(DocumentType.RFI_RESPONSE, RFI_DOC, supersedes=frozenset({SPEC_DOC}))

        outcome = resolve([spec, rfi])

        superseded = next(r for r in outcome.ranked if r.candidate == spec)
        assert superseded.superseded_by == RFI_DOC

    def test_an_rfi_answering_a_different_document_does_not_supersede_this_one(self) -> None:
        spec = candidate(DocumentType.SPEC_SECTION, SPEC_DOC)
        rfi = candidate(DocumentType.RFI_RESPONSE, RFI_DOC, supersedes=frozenset({OTHER_SPEC_DOC}))

        outcome = resolve([spec, rfi])

        # The RFI still outranks by document type, but the spec is not marked
        # superseded, because this RFI did not answer it.
        assert outcome.resolved
        assert outcome.winner == rfi
        assert all(r.superseded_by is None for r in outcome.ranked)


class TestThingsTheRulesWillNotSettle:
    def test_a_safety_conflict_is_always_sent_to_a_person(self) -> None:
        """Whatever the hierarchy says, a person decides which safety rule stands."""
        spec = candidate(DocumentType.SPEC_SECTION, SPEC_DOC, criticality=Criticality.SAFETY)
        submittal = candidate(DocumentType.APPROVED_SUBMITTAL, SUBMITTAL_DOC)

        outcome = resolve([spec, submittal])

        assert outcome.resolution is Resolution.CONFLICT
        assert outcome.winner is None
        assert "safety" in (outcome.conflict_reason or "").lower()

    def test_a_lone_safety_requirement_still_resolves(self) -> None:
        """The rule is about conflicts, not about safety requirements existing."""
        spec = candidate(DocumentType.SPEC_SECTION, SPEC_DOC, criticality=Criticality.SAFETY)
        outcome = resolve([spec])
        assert outcome.resolved

    def test_two_documents_of_the_same_type_are_not_ranked_against_each_other(self) -> None:
        outcome = resolve(
            [
                candidate(DocumentType.SPEC_SECTION, SPEC_DOC),
                candidate(DocumentType.SPEC_SECTION, OTHER_SPEC_DOC),
            ]
        )

        assert outcome.resolution is Resolution.CONFLICT
        assert "same type" in (outcome.conflict_reason or "")

    def test_two_requirements_from_one_document_are_not_a_conflict(self) -> None:
        """One document saying two things is a grouping question, not a precedence one."""
        outcome = resolve(
            [
                candidate(DocumentType.SPEC_SECTION, SPEC_DOC),
                candidate(DocumentType.SPEC_SECTION, SPEC_DOC),
            ]
        )
        assert outcome.resolved

    def test_a_standard_disagreeing_with_another_document_is_surfaced(self) -> None:
        """The architecture doc never says where a referenced standard ranks."""
        spec = candidate(DocumentType.SPEC_SECTION, SPEC_DOC)
        standard = candidate(DocumentType.STANDARD, STANDARD_DOC)

        outcome = resolve([spec, standard])

        assert outcome.resolution is Resolution.CONFLICT
        assert "standard" in (outcome.conflict_reason or "").lower()

    def test_an_empty_group_is_a_conflict_not_a_crash(self) -> None:
        outcome = resolve([])
        assert outcome.resolution is Resolution.CONFLICT
        assert outcome.winner is None

    def test_everything_superseded_by_an_absent_rfi_is_surfaced(self) -> None:
        """The RFI that supersedes these is not in the group, so nothing is left to apply."""
        spec = Candidate(
            requirement_id=uuid.uuid4(),
            document_id=SPEC_DOC,
            doc_type=DocumentType.SPEC_SECTION,
            criticality=Criticality.QUALITY,
        )
        rfi_pointing_at_spec = candidate(
            DocumentType.RFI_RESPONSE, RFI_DOC, supersedes=frozenset({SPEC_DOC, RFI_DOC})
        )

        outcome = resolve([spec, rfi_pointing_at_spec])

        assert outcome.resolution is Resolution.CONFLICT
        assert "superseded" in (outcome.conflict_reason or "")
