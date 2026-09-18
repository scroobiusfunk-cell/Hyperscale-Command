"""PDF in, draft requirements out.

The end-to-end path the Requirements Compiler exists to provide, with a fake
model provider standing in for the one place a model appears.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.ingestion.service import ingest_pdf
from app.llm.base import LLMError, PromptSpec
from app.llm.fake import FakeProvider
from app.models import Project, Requirement, RuleSet, SourceDocument
from app.models.enums import Criticality, DocumentType, RequirementStatus
from app.requirements_compiler.compile import CompileRefusedError, compile_document
from app.requirements_compiler.precedence import BASE_RANK
from app.requirements_compiler.schema import (
    AppliesTo,
    ExtractedRequirement,
    ExtractionResponse,
    PresenceCriteria,
)
from app.storage import InMemoryStorage
from tests import factories as f
from tests.pdfs import SPEC_SECTION_LINES, imageless_scan_pdf, text_pdf

BUCKET = "understudy-documents"


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


@pytest.fixture
def rule_set(db: Session, project: Project) -> RuleSet:
    return f.make_rule_set(db, project, "1.0.0")


def ingest(db: Session, project: Project, data: bytes) -> SourceDocument:
    return ingest_pdf(
        db,
        InMemoryStorage(),
        project_id=project.id,
        doc_type=DocumentType.SPEC_SECTION,
        title="26 05 00",
        data=data,
        bucket=BUCKET,
    ).document


def one_requirement_per_section(
    criticality: Criticality = Criticality.QUALITY,
    uncertain: list[str] | None = None,
    subject: str = "equipment nameplate",
) -> FakeProvider:
    def handler(spec: PromptSpec, section_text: str) -> ExtractionResponse:
        first_line = section_text.strip().splitlines()[-1][:80]
        return ExtractionResponse(
            requirements=[
                ExtractedRequirement(
                    applies_to=AppliesTo(equipment_class=["switchboard"]),
                    statement=first_line,
                    check_subject=subject,
                    verification_method="visual",
                    pass_criteria=PresenceCriteria(
                        kind="presence", expected="present", subject="label"
                    ),
                    criticality=criticality,
                    source_clause="26 05 00 - 1.7",
                    source_page=1,
                    why_it_matters="Somebody opening this board needs to know what is inside.",
                    uncertain_about=uncertain or [],
                )
            ]
        )

    return FakeProvider(handler=handler)


class TestTheWholePath:
    def test_a_spec_pdf_becomes_draft_requirements(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        document = ingest(db, project, text_pdf([SPEC_SECTION_LINES]))

        report = compile_document(
            db,
            one_requirement_per_section(),
            document_id=document.id,
            rule_set_id=rule_set.id,
        )

        assert report.sections == 2, "one per lettered paragraph"
        assert report.created == 2
        assert report.clean

        requirements = db.query(Requirement).filter_by(rule_set_id=rule_set.id).all()
        assert len(requirements) == 2
        assert {r.ruleset_version for r in requirements} == {"1.0.0"}

    def test_nothing_compiled_is_approved(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        """Only a person publishing a rule set can put a requirement in front of a tech."""
        document = ingest(db, project, text_pdf([SPEC_SECTION_LINES]))
        compile_document(
            db, one_requirement_per_section(), document_id=document.id, rule_set_id=rule_set.id
        )

        statuses = {r.status for r in db.query(Requirement).all()}
        assert RequirementStatus.APPROVED not in statuses

    def test_safety_requirements_land_in_the_review_pile(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        document = ingest(db, project, text_pdf([SPEC_SECTION_LINES]))

        report = compile_document(
            db,
            one_requirement_per_section(criticality=Criticality.SAFETY),
            document_id=document.id,
            rule_set_id=rule_set.id,
        )

        assert report.needing_review == report.created
        assert all(r.status is RequirementStatus.NEEDS_REVIEW for r in db.query(Requirement).all())

    def test_precedence_rank_comes_from_the_document_type(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        document = ingest(db, project, text_pdf([SPEC_SECTION_LINES]))
        compile_document(
            db, one_requirement_per_section(), document_id=document.id, rule_set_id=rule_set.id
        )

        ranks = {r.precedence_rank for r in db.query(Requirement).all()}
        assert ranks == {BASE_RANK[DocumentType.SPEC_SECTION]}

    def test_the_source_clause_and_page_survive_into_the_record(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        """A requirement that cannot point at its clause is not curatable."""
        document = ingest(db, project, text_pdf([SPEC_SECTION_LINES]))
        compile_document(
            db, one_requirement_per_section(), document_id=document.id, rule_set_id=rule_set.id
        )

        requirement = db.query(Requirement).first()
        assert requirement is not None
        assert requirement.source_doc_id == document.id
        assert requirement.source_clause
        assert requirement.source_page >= 1


class TestWhenThingsGoWrong:
    def test_a_scanned_document_is_refused_with_a_reason(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        document = ingest(db, project, imageless_scan_pdf())

        with pytest.raises(CompileRefusedError, match="no text layer"):
            compile_document(
                db,
                one_requirement_per_section(),
                document_id=document.id,
                rule_set_id=rule_set.id,
            )

    def test_one_failing_section_does_not_abandon_the_document(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        document = ingest(db, project, text_pdf([SPEC_SECTION_LINES]))

        calls = {"n": 0}

        def flaky(spec: PromptSpec, section_text: str) -> ExtractionResponse:
            calls["n"] += 1
            if calls["n"] == 1:
                raise LLMError("the provider timed out")
            return ExtractionResponse(
                requirements=[
                    ExtractedRequirement(
                        applies_to=AppliesTo(equipment_class=["switchboard"]),
                        statement="Provide a nameplate.",
                        check_subject="equipment nameplate",
                        verification_method="visual",
                        pass_criteria=PresenceCriteria(
                            kind="presence", expected="present", subject="nameplate"
                        ),
                        criticality=Criticality.QUALITY,
                        source_clause="26 05 00 - 1.7",
                        source_page=1,
                        why_it_matters="A mislabelled panel sends the next person wrong.",
                    )
                ]
            )

        report = compile_document(
            db,
            FakeProvider(handler=flaky),
            document_id=document.id,
            rule_set_id=rule_set.id,
        )

        assert report.created == 1
        assert not report.clean
        assert len(report.failed_sections) == 1
        assert report.failed_sections[0].startswith("26 05 00")

    def test_an_unknown_document_is_refused(self, db: Session, rule_set: RuleSet) -> None:
        import uuid

        with pytest.raises(CompileRefusedError, match="No document"):
            compile_document(
                db,
                one_requirement_per_section(),
                document_id=uuid.uuid4(),
                rule_set_id=rule_set.id,
            )


class TestTwoDocumentsGoverningTheSameCheck:
    """The thing Q17 left undone: a spec and its submittal disagreeing."""

    def _ingest_as(
        self, db: Session, project: Project, doc_type: DocumentType, title: str, body: str
    ) -> SourceDocument:
        return ingest_pdf(
            db,
            InMemoryStorage(),
            project_id=project.id,
            doc_type=doc_type,
            title=title,
            data=text_pdf([["1.7 FIELD QUALITY CONTROL", "", f"A. {body}"]]),
            bucket=BUCKET,
        ).document

    def test_a_spec_and_a_submittal_on_the_same_check_are_ranked(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        from app.requirements_compiler.grouping import open_conflicts, resolve_precedence

        spec = self._ingest_as(
            db,
            project,
            DocumentType.SPEC_SECTION,
            "26 05 00",
            "Each switchboard shall bear an equipment nameplate.",
        )
        submittal = self._ingest_as(
            db,
            project,
            DocumentType.APPROVED_SUBMITTAL,
            "Switchboard submittal",
            "Nameplates shall be engraved laminated phenolic.",
        )

        for document in (spec, submittal):
            compile_document(
                db,
                one_requirement_per_section(),
                document_id=document.id,
                rule_set_id=rule_set.id,
            )

        report = resolve_precedence(db, rule_set.id)

        assert report.contested == 1, "the same check_subject from two documents"
        assert report.resolved == 1
        assert open_conflicts(db, rule_set.id) == []

        by_doc = {r.source_doc_id: r for r in db.query(Requirement).all()}
        assert by_doc[spec.id].precedence_rank < by_doc[submittal.id].precedence_rank

    def test_a_safety_disagreement_between_them_is_surfaced(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        from app.requirements_compiler.grouping import open_conflicts, resolve_precedence

        spec = self._ingest_as(
            db,
            project,
            DocumentType.SPEC_SECTION,
            "26 05 00",
            "Each switchboard shall bear an arc flash warning label.",
        )
        submittal = self._ingest_as(
            db,
            project,
            DocumentType.APPROVED_SUBMITTAL,
            "Switchboard submittal",
            "Arc flash labels are supplied by the manufacturer.",
        )

        for document in (spec, submittal):
            compile_document(
                db,
                one_requirement_per_section(criticality=Criticality.SAFETY),
                document_id=document.id,
                rule_set_id=rule_set.id,
            )

        resolve_precedence(db, rule_set.id)

        conflicts = open_conflicts(db, rule_set.id)
        assert len(conflicts) == 1
        assert "safety" in conflicts[0].reason.lower()

    def test_different_checks_from_the_two_documents_do_not_collide(
        self, db: Session, project: Project, rule_set: RuleSet
    ) -> None:
        from app.requirements_compiler.grouping import resolve_precedence

        spec = self._ingest_as(
            db, project, DocumentType.SPEC_SECTION, "26 05 00", "Nameplates required."
        )
        submittal = self._ingest_as(
            db,
            project,
            DocumentType.APPROVED_SUBMITTAL,
            "Submittal",
            "Arc flash labels supplied.",
        )

        compile_document(
            db,
            one_requirement_per_section(subject="equipment nameplate"),
            document_id=spec.id,
            rule_set_id=rule_set.id,
        )
        compile_document(
            db,
            one_requirement_per_section(subject="arc flash warning label"),
            document_id=submittal.id,
            rule_set_id=rule_set.id,
        )

        report = resolve_precedence(db, rule_set.id)

        assert report.groups == 2
        assert report.contested == 0
