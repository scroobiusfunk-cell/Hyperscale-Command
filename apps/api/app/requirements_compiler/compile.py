"""Compiling an ingested document into a draft rule set.

Ties the pieces together: sections in, extraction per section, Requirement rows
out. Everything lands in a *draft* rule set — nothing this function does can put
a requirement in front of a tech, because only a person publishing a rule set
can do that.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.capture.recipes import evidence_spec_for, recipe_for_criteria
from app.ingestion.service import sections_for
from app.llm.base import LLMProvider, PromptSpec
from app.logging import get_logger
from app.models import Requirement, RuleSet, SourceDocument
from app.models.enums import TextLayerStatus
from app.requirements_compiler.extraction import (
    EXTRACTION_PROMPT_V1,
    ExtractionOutcome,
    extract_from_section,
)
from app.requirements_compiler.grouping import compute_check_key
from app.requirements_compiler.precedence import BASE_RANK
from app.requirements_compiler.schema import UnplaceableSpan

log = get_logger(__name__)


class CompileRefusedError(RuntimeError):
    """The document cannot be compiled without a person doing something first."""


@dataclass(frozen=True)
class CompileReport:
    document_id: uuid.UUID
    rule_set_id: uuid.UUID
    sections: int = 0
    created: int = 0
    needing_review: int = 0
    unplaceable: tuple[UnplaceableSpan, ...] = ()
    failed_sections: tuple[str, ...] = field(default=())

    @property
    def clean(self) -> bool:
        return not self.failed_sections


def compile_document(
    session: Session,
    provider: LLMProvider,
    *,
    document_id: uuid.UUID,
    rule_set_id: uuid.UUID,
    spec: PromptSpec = EXTRACTION_PROMPT_V1,
) -> CompileReport:
    """Extract every section of a document into a draft rule set."""
    document = session.get(SourceDocument, document_id)
    if document is None:
        raise CompileRefusedError(f"No document {document_id}.")
    if document.text_layer_status is TextLayerStatus.MISSING:
        raise CompileRefusedError(
            f"{document.title} has no text layer, so there is nothing to extract from. "
            "A person needs to supply a text-bearing copy. See OPEN_QUESTIONS Q2."
        )

    rule_set = session.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise CompileRefusedError(f"No rule set {rule_set_id}.")

    sections = sections_for(session, document_id)
    created = 0
    needing_review = 0
    unplaceable: list[UnplaceableSpan] = []
    failed: list[str] = []

    for section in sections:
        outcome: ExtractionOutcome = extract_from_section(
            provider, document_id=document_id, section_text=section.text, spec=spec
        )
        if not outcome.succeeded:
            # One bad section does not abandon the document; the failure is
            # reported so a person can re-run or read that clause themselves.
            failed.append(section.full_clause)
            continue

        unplaceable.extend(outcome.unplaceable)

        for compiled in outcome.requirements:
            extracted = compiled.extracted
            criteria = extracted.pass_criteria.model_dump(mode="json")
            # A requirement with nothing to capture cannot be approved — there
            # is a check constraint saying so — and a curator has no way to
            # invent a recipe. So compilation points it at one, and a
            # requirement whose method has no Phase 1 recipe stays unpointed and
            # visibly unapprovable rather than quietly approvable and unwalkable.
            recipe = recipe_for_criteria(extracted.verification_method, criteria)
            evidence_spec = evidence_spec_for(session, recipe) if recipe else []
            session.add(
                Requirement(
                    id=uuid.uuid4(),
                    project_id=document.project_id,
                    rule_set_id=rule_set.id,
                    ruleset_version=rule_set.version,
                    applies_to_equipment_class=list(extracted.applies_to.equipment_class),
                    applies_to_system=extracted.applies_to.system,
                    applies_to_location_type=extracted.applies_to.location_type,
                    statement=extracted.statement,
                    verification_method=extracted.verification_method,
                    evidence_spec=evidence_spec,
                    pass_criteria=criteria,
                    criticality=extracted.criticality,
                    access_constraints=list(extracted.access_constraints),
                    source_doc_id=document.id,
                    source_clause=extracted.source_clause,
                    source_page=extracted.source_page,
                    check_key=compute_check_key(
                        equipment_class=list(extracted.applies_to.equipment_class),
                        system=extracted.applies_to.system,
                        location_type=extracted.applies_to.location_type,
                        check_subject=extracted.check_subject,
                    ),
                    # A starting rank from the document type. Once a second
                    # document is compiled into the same rule set,
                    # resolve_precedence regrades every contested group.
                    precedence_rank=BASE_RANK[document.doc_type],
                    why_it_matters=extracted.why_it_matters,
                    status=compiled.status,
                )
            )
            created += 1
            if compiled.needs_review_because:
                needing_review += 1

    session.flush()

    log.info(
        "compile.completed",
        document_id=str(document_id),
        rule_set_id=str(rule_set_id),
        sections=len(sections),
        created=created,
        needing_review=needing_review,
        unplaceable=len(unplaceable),
        failed_sections=len(failed),
    )

    return CompileReport(
        document_id=document_id,
        rule_set_id=rule_set_id,
        sections=len(sections),
        created=created,
        needing_review=needing_review,
        unplaceable=tuple(unplaceable),
        failed_sections=tuple(failed),
    )
