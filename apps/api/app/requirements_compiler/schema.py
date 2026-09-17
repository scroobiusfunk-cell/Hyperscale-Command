"""The strict schema the extraction model must answer in.

Two things are deliberately absent. `precedence_rank` is not here because
precedence is resolved by code from document types, not proposed by a model
reading one document in isolation. `status` is not here either: whether a
requirement is fit to go live is a decision about the whole rule set and the
people who approved it, and a model that could set its own status could mark
its own guesses approved.

`why_it_matters` is present but is a *draft*. The architecture doc requires it to
be written or approved by a human, which curation enforces.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.enums import Criticality, VerificationMethod


class PresenceCriteria(BaseModel):
    kind: Literal["presence"]
    expected: Literal["present", "absent"]
    subject: str = Field(min_length=1, description="What must be present or absent, in plain words")


class PatternCriteria(BaseModel):
    kind: Literal["pattern"]
    pattern: str = Field(min_length=1, description="Regular expression applied to normalized text")
    description: str = Field(min_length=1, description="The same rule in plain words, for the tech")
    case_sensitive: bool = False


class ExpectedValueCriteria(BaseModel):
    kind: Literal["expected_value"]
    value: str | float | bool
    unit: str | None = None
    source_of_truth: Literal["submittal", "schedule", "specification", "literal"]


class ToleranceCriteria(BaseModel):
    kind: Literal["tolerance"]
    nominal: float
    plus: float = Field(ge=0)
    minus: float = Field(ge=0)
    unit: str = Field(min_length=1)


PassCriteria = Annotated[
    PresenceCriteria | PatternCriteria | ExpectedValueCriteria | ToleranceCriteria,
    Field(discriminator="kind"),
]


class AppliesTo(BaseModel):
    equipment_class: list[str] = Field(
        min_length=1, description="snake_case equipment classes this requirement governs"
    )
    system: str | None = Field(
        default=None, description="Null when the requirement applies to every system"
    )
    location_type: str | None = Field(
        default=None, description="Null when the requirement applies in every location type"
    )


class ExtractedRequirement(BaseModel):
    """One requirement as the model read it."""

    applies_to: AppliesTo
    statement: str = Field(min_length=1, description="Plain language, as the tech will read it")
    verification_method: VerificationMethod
    pass_criteria: PassCriteria
    criticality: Criticality
    source_clause: str = Field(min_length=1)
    source_page: int = Field(ge=1)
    why_it_matters: str = Field(
        min_length=1, description="Draft only. A human writes or approves the final wording."
    )
    uncertain_about: list[str] = Field(
        default_factory=list,
        description=(
            "Name any field you were not confident about, rather than picking a plausible "
            "value. Anything named here sends the requirement to a person."
        ),
    )


class UnplaceableSpan(BaseModel):
    """Text that states a requirement the model could not turn into a record."""

    source_clause: str = Field(min_length=1)
    source_page: int = Field(ge=1)
    text: str = Field(min_length=1)
    reason: str = Field(min_length=1, description="Why it could not be placed, in plain words")


class ExtractionResponse(BaseModel):
    """The model's whole answer for one document section."""

    requirements: list[ExtractedRequirement] = Field(default_factory=list)
    unplaceable: list[UnplaceableSpan] = Field(
        default_factory=list,
        description=(
            "Requirements you can see in the text but cannot place. Put them here rather "
            "than guessing; a missed requirement a person can see beats an invented one."
        ),
    )
