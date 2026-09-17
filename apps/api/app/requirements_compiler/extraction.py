"""Extracting requirements from one document section.

The model proposes; code decides what happens to the proposal. In particular
code, not the model, sets `status`, and the rules for doing so are deliberately
pessimistic: a requirement reaches a tech only after a person has approved it,
and anything the model was unsure about is flagged before a person ever sees it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.llm.base import LLMError, LLMProvider, PromptSpec
from app.logging import get_logger
from app.models.enums import Criticality, RequirementStatus
from app.requirements_compiler.schema import (
    ExtractedRequirement,
    ExtractionResponse,
    UnplaceableSpan,
)

log = get_logger(__name__)

EXTRACTION_SYSTEM_PROMPT = """\
You read one section of a construction document and turn the requirements in it \
into structured records for a commissioning inspection tool.

A requirement is something a person could stand in front of the equipment and \
check. "Provide a switchboard" is scope, not a requirement. "Each switchboard \
shall have an arc flash warning label on the front" is a requirement.

Rules:

- One record per requirement. If a clause states three checkable things, that is \
three records.
- Write `statement` and `why_it_matters` in plain language, for a field tech who \
has not read the specification. No jargon, no clause numbers inside the text.
- `why_it_matters` says what fails in service if this is missed. If you do not \
know, say so in `uncertain_about` rather than writing something generic.
- Use `criticality: safety` for anything gating energization, arc-flash labelling \
and clearances, grounding and bonding, protective device settings, lock-out \
tag-out verifications, fire and life-safety systems, or confined-space and fall \
protection conditions. When unsure whether something is a safety item, mark it \
safety and name the doubt in `uncertain_about`.
- Never invent a value to fill a field. If you cannot tell which equipment class \
a requirement governs, or what the pass criteria are, name that field in \
`uncertain_about`.
- If you can see a requirement in the text but cannot turn it into a record, put \
it in `unplaceable` with the reason. A requirement a person has to place by hand \
is much better than one you guessed at.
- Quote `source_clause` exactly as the document numbers it, and give the page it \
appears on.
"""

#: Pinned as a unit: prompt text, model and version. Changing any of them means a
#: new version here, so the eval harness can tell two runs apart.
EXTRACTION_PROMPT_V1 = PromptSpec(
    prompt_id="requirements.extract",
    version="1.0.0",
    model="claude-opus-5",
    system=EXTRACTION_SYSTEM_PROMPT,
    max_tokens=16_000,
)


@dataclass(frozen=True)
class CompiledRequirement:
    """An extracted requirement with the decisions code makes about it."""

    extracted: ExtractedRequirement
    status: RequirementStatus
    needs_review_because: tuple[str, ...]

    @property
    def is_safety(self) -> bool:
        return self.extracted.criticality is Criticality.SAFETY


@dataclass(frozen=True)
class ExtractionOutcome:
    document_id: uuid.UUID
    requirements: tuple[CompiledRequirement, ...] = ()
    unplaceable: tuple[UnplaceableSpan, ...] = ()
    failure: str | None = None
    prompt_id: str = EXTRACTION_PROMPT_V1.prompt_id
    prompt_version: str = EXTRACTION_PROMPT_V1.version
    model: str = EXTRACTION_PROMPT_V1.model

    @property
    def succeeded(self) -> bool:
        return self.failure is None

    @property
    def needing_review(self) -> tuple[CompiledRequirement, ...]:
        return tuple(r for r in self.requirements if r.status is RequirementStatus.NEEDS_REVIEW)


def classify(extracted: ExtractedRequirement) -> CompiledRequirement:
    """Decide what status an extracted requirement starts life in.

    Nothing here can produce `approved`. Approval is a person's act, recorded
    against their identity, and no extraction run is allowed to shortcut it.
    """
    reasons: list[str] = []

    if extracted.uncertain_about:
        reasons.append(
            "The model was unsure about: " + ", ".join(sorted(extracted.uncertain_about)) + "."
        )

    if extracted.criticality is Criticality.SAFETY:
        # Not a sign of a bad extraction; safety items simply never go live
        # unapproved, so they start in the reviewer's pile by construction.
        reasons.append("Safety requirements are always read by a qualified person.")

    status = RequirementStatus.NEEDS_REVIEW if reasons else RequirementStatus.DRAFT
    return CompiledRequirement(
        extracted=extracted, status=status, needs_review_because=tuple(reasons)
    )


def extract_from_section(
    provider: LLMProvider,
    *,
    document_id: uuid.UUID,
    section_text: str,
    spec: PromptSpec = EXTRACTION_PROMPT_V1,
) -> ExtractionOutcome:
    """Extract requirements from one section, or report why it could not.

    A failure returns an outcome carrying the reason rather than raising, so a
    compile run over a hundred sections records the sections that failed instead
    of stopping at the first one. It never returns a partial or invented record.
    """
    if not section_text.strip():
        return ExtractionOutcome(document_id=document_id, failure="The section text was empty.")

    try:
        result = provider.complete_structured(
            spec,
            section_text,
            ExtractionResponse,
            context={"document_id": str(document_id)},
        )
    except LLMError as exc:
        log.warning(
            "extraction.failed",
            document_id=str(document_id),
            prompt_id=spec.prompt_id,
            prompt_version=spec.version,
            model=spec.model,
            error=str(exc),
        )
        return ExtractionOutcome(
            document_id=document_id,
            failure=str(exc),
            prompt_id=spec.prompt_id,
            prompt_version=spec.version,
            model=spec.model,
        )

    compiled = tuple(classify(r) for r in result.output.requirements)

    log.info(
        "extraction.completed",
        document_id=str(document_id),
        prompt_id=spec.prompt_id,
        prompt_version=spec.version,
        model=spec.model,
        extracted=len(compiled),
        needs_review=sum(1 for c in compiled if c.status is RequirementStatus.NEEDS_REVIEW),
        unplaceable=len(result.output.unplaceable),
    )

    return ExtractionOutcome(
        document_id=document_id,
        requirements=compiled,
        unplaceable=tuple(result.output.unplaceable),
        prompt_id=spec.prompt_id,
        prompt_version=spec.version,
        model=spec.model,
    )
