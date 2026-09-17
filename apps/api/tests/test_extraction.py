"""Extraction: what the model proposes, and what code decides about it.

Every test runs against the fake provider. Nothing here touches a network, an
API key, or a real model.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.llm.base import LLMError, LLMRefusalError, PromptSpec
from app.llm.fake import FakeProvider
from app.models.enums import Criticality, RequirementStatus, VerificationMethod
from app.requirements_compiler.extraction import (
    EXTRACTION_PROMPT_V1,
    extract_from_section,
)
from app.requirements_compiler.schema import (
    AppliesTo,
    ExtractedRequirement,
    ExtractionResponse,
    PresenceCriteria,
    UnplaceableSpan,
)

DOCUMENT_ID = uuid.UUID("cccccccc-0000-4000-8000-000000000001")


def a_requirement(
    *,
    criticality: Criticality = Criticality.QUALITY,
    uncertain_about: list[str] | None = None,
) -> ExtractedRequirement:
    return ExtractedRequirement(
        applies_to=AppliesTo(
            equipment_class=["switchboard"],
            system="normal_power",
            location_type="electrical_room",
        ),
        statement="The equipment nameplate shows the panel tag.",
        verification_method=VerificationMethod.VISUAL,
        pass_criteria=PresenceCriteria(
            kind="presence", expected="present", subject="equipment nameplate"
        ),
        criticality=criticality,
        source_clause="26 05 53 - 2.1.A",
        source_page=3,
        why_it_matters="A mislabelled panel sends the next person to the wrong board.",
        uncertain_about=uncertain_about or [],
    )


def responding_with(*requirements: ExtractedRequirement, **kwargs: object) -> FakeProvider:
    return FakeProvider([ExtractionResponse(requirements=list(requirements), **kwargs)])


class TestCodeDecidesStatusNotTheModel:
    def test_a_confident_non_safety_requirement_starts_as_draft(self) -> None:
        outcome = extract_from_section(
            responding_with(a_requirement()),
            document_id=DOCUMENT_ID,
            section_text="Each switchboard shall bear a nameplate.",
        )

        assert outcome.succeeded
        assert outcome.requirements[0].status is RequirementStatus.DRAFT

    def test_anything_the_model_was_unsure_about_goes_to_a_person(self) -> None:
        outcome = extract_from_section(
            responding_with(a_requirement(uncertain_about=["pass_criteria"])),
            document_id=DOCUMENT_ID,
            section_text="Nameplates as indicated.",
        )

        compiled = outcome.requirements[0]
        assert compiled.status is RequirementStatus.NEEDS_REVIEW
        assert "pass_criteria" in compiled.needs_review_because[0]

    def test_a_safety_requirement_always_goes_to_a_person(self) -> None:
        """Nothing with criticality safety goes live unapproved."""
        outcome = extract_from_section(
            responding_with(a_requirement(criticality=Criticality.SAFETY)),
            document_id=DOCUMENT_ID,
            section_text="Arc flash labelling shall be provided.",
        )

        compiled = outcome.requirements[0]
        assert compiled.status is RequirementStatus.NEEDS_REVIEW
        assert compiled.is_safety
        assert any("qualified person" in reason for reason in compiled.needs_review_because)

    def test_extraction_can_never_produce_an_approved_requirement(self) -> None:
        """Approval is a person's act. No extraction run may shortcut it."""
        outcome = extract_from_section(
            responding_with(
                a_requirement(),
                a_requirement(criticality=Criticality.SAFETY),
                a_requirement(uncertain_about=["criticality"]),
            ),
            document_id=DOCUMENT_ID,
            section_text="Several requirements.",
        )

        statuses = {r.status for r in outcome.requirements}
        assert RequirementStatus.APPROVED not in statuses
        assert statuses <= {RequirementStatus.DRAFT, RequirementStatus.NEEDS_REVIEW}


class TestFailuresDoNotBecomeRequirements:
    def test_a_provider_error_is_reported_not_raised(self) -> None:
        """A compile run over a hundred sections records failures and continues."""
        outcome = extract_from_section(
            FakeProvider([LLMError("provider exploded")]),
            document_id=DOCUMENT_ID,
            section_text="Some section text.",
        )

        assert not outcome.succeeded
        assert outcome.requirements == ()
        assert "provider exploded" in (outcome.failure or "")

    def test_a_refusal_is_reported_the_same_way(self) -> None:
        outcome = extract_from_section(
            FakeProvider([LLMRefusalError("declined")]),
            document_id=DOCUMENT_ID,
            section_text="Some section text.",
        )

        assert not outcome.succeeded
        assert outcome.requirements == ()

    def test_empty_section_text_never_reaches_the_provider(self) -> None:
        provider = FakeProvider([])
        outcome = extract_from_section(provider, document_id=DOCUMENT_ID, section_text="   \n  ")

        assert not outcome.succeeded
        assert provider.calls == [], "no reason to pay for a call on empty text"


class TestWhatTheModelCouldNotPlace:
    def test_unplaceable_spans_are_kept_for_a_person(self) -> None:
        """A requirement a person has to place by hand beats an invented one."""
        provider = responding_with(
            a_requirement(),
            unplaceable=[
                UnplaceableSpan(
                    source_clause="26 05 00 - 3.4",
                    source_page=11,
                    text="Coordinate with Division 23 as required.",
                    reason="No checkable condition; it points at another section.",
                )
            ],
        )

        outcome = extract_from_section(provider, document_id=DOCUMENT_ID, section_text="...")

        assert len(outcome.unplaceable) == 1
        assert outcome.unplaceable[0].source_page == 11


class TestThePromptIsPinned:
    def test_the_outcome_records_the_prompt_and_model_it_used(self) -> None:
        """The eval harness compares runs by these three fields."""
        outcome = extract_from_section(
            responding_with(a_requirement()), document_id=DOCUMENT_ID, section_text="..."
        )

        assert outcome.prompt_id == "requirements.extract"
        assert outcome.prompt_version == EXTRACTION_PROMPT_V1.version
        assert outcome.model == EXTRACTION_PROMPT_V1.model

    def test_a_failure_still_records_which_version_failed(self) -> None:
        outcome = extract_from_section(
            FakeProvider([LLMError("nope")]), document_id=DOCUMENT_ID, section_text="..."
        )

        assert outcome.prompt_version == EXTRACTION_PROMPT_V1.version
        assert outcome.model == EXTRACTION_PROMPT_V1.model

    def test_the_provider_is_called_with_the_pinned_spec(self) -> None:
        provider = responding_with(a_requirement())
        extract_from_section(provider, document_id=DOCUMENT_ID, section_text="hello")

        spec, user_content = provider.calls[0]
        assert spec is EXTRACTION_PROMPT_V1
        assert user_content == "hello"

    def test_a_different_pinned_spec_is_recorded_as_such(self) -> None:
        """Swapping the spec is how the eval harness compares providers."""
        alternative = PromptSpec(
            prompt_id="requirements.extract",
            version="2.0.0-experiment",
            model="claude-sonnet-5",
            system="different wording",
        )

        outcome = extract_from_section(
            responding_with(a_requirement()),
            document_id=DOCUMENT_ID,
            section_text="...",
            spec=alternative,
        )

        assert outcome.prompt_version == "2.0.0-experiment"
        assert outcome.model == "claude-sonnet-5"


class TestTheSchemaIsStrict:
    def test_an_unknown_criticality_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedRequirement(
                applies_to=AppliesTo(equipment_class=["switchboard"]),
                statement="x",
                verification_method=VerificationMethod.VISUAL,
                pass_criteria=PresenceCriteria(
                    kind="presence", expected="present", subject="nameplate"
                ),
                criticality="informational",
                source_clause="1.1",
                source_page=1,
                why_it_matters="x",
            )

    def test_a_requirement_governing_no_equipment_class_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AppliesTo(equipment_class=[])

    def test_an_empty_statement_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedRequirement(
                applies_to=AppliesTo(equipment_class=["switchboard"]),
                statement="",
                verification_method=VerificationMethod.VISUAL,
                pass_criteria=PresenceCriteria(
                    kind="presence", expected="present", subject="nameplate"
                ),
                criticality=Criticality.QUALITY,
                source_clause="1.1",
                source_page=1,
                why_it_matters="x",
            )

    def test_a_page_number_below_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UnplaceableSpan(source_clause="1.1", source_page=0, text="x", reason="y")

    def test_pass_criteria_must_be_one_of_the_known_kinds(self) -> None:
        with pytest.raises(ValidationError):
            ExtractionResponse.model_validate(
                {
                    "requirements": [
                        {
                            "applies_to": {"equipment_class": ["switchboard"]},
                            "statement": "x",
                            "verification_method": "visual",
                            "pass_criteria": {"kind": "vibes", "subject": "nameplate"},
                            "criticality": "quality",
                            "source_clause": "1.1",
                            "source_page": 1,
                            "why_it_matters": "x",
                        }
                    ]
                }
            )
