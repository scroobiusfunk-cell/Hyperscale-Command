"""Ingestion, against real PDFs built at test time."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.ingestion.pdf import PdfReadError, read_pdf
from app.ingestion.service import ingest_pdf, sections_for
from app.models import DocumentPage, Project, SourceDocument
from app.models.enums import DocumentType, TextLayerStatus
from app.storage import InMemoryStorage, StorageError
from tests import factories as f
from tests.pdfs import SPEC_SECTION_LINES, imageless_scan_pdf, text_pdf

BUCKET = "fie-documents"


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def project(db: Session) -> Project:
    return f.make_project(db)


class TestReadingAPdf:
    def test_text_and_a_page_image_come_back_for_every_page(self) -> None:
        parsed = read_pdf(text_pdf([["Page one text here."], ["Page two text here."]]))

        assert parsed.page_count == 2
        assert [p.page_number for p in parsed.pages] == [1, 2]
        assert "Page one" in parsed.pages[0].text
        assert parsed.pages[0].image_png.startswith(b"\x89PNG")

    def test_a_document_with_text_is_marked_present(self) -> None:
        parsed = read_pdf(text_pdf([SPEC_SECTION_LINES]))
        assert parsed.text_layer_status is TextLayerStatus.PRESENT
        assert parsed.is_readable

    def test_a_scan_is_marked_missing_rather_than_coming_back_empty(self) -> None:
        """Phase 1 has no OCR. A scan is a thing a person needs to know about."""
        parsed = read_pdf(imageless_scan_pdf(page_count=2))

        assert parsed.text_layer_status is TextLayerStatus.MISSING
        assert not parsed.is_readable
        assert parsed.page_count == 2, "the page images are still worth having"

    def test_a_mostly_text_document_is_partial_not_missing(self) -> None:
        """A spec with a scanned signature page is still worth extracting from."""
        parsed = read_pdf(text_pdf([SPEC_SECTION_LINES, SPEC_SECTION_LINES, []]))
        assert parsed.text_layer_status is TextLayerStatus.PARTIAL
        assert parsed.is_readable

    @pytest.mark.parametrize(
        ("data", "match"),
        [(b"", "empty"), (b"this is not a pdf at all", "Could not open")],
    )
    def test_unreadable_input_raises_rather_than_returning_half_a_document(
        self, data: bytes, match: str
    ) -> None:
        """A half-read spec would silently drop requirements."""
        with pytest.raises(PdfReadError, match=match):
            read_pdf(data)


class TestIngesting:
    def test_pages_and_images_are_stored(
        self, db: Session, storage: InMemoryStorage, project: Project
    ) -> None:
        result = ingest_pdf(
            db,
            storage,
            project_id=project.id,
            doc_type=DocumentType.SPEC_SECTION,
            title="26 05 00",
            data=text_pdf([SPEC_SECTION_LINES]),
            bucket=BUCKET,
        )

        assert result.pages_ingested == 1
        assert result.document.text_layer_status is TextLayerStatus.PRESENT

        pages = db.query(DocumentPage).filter_by(document_id=result.document.id).all()
        assert len(pages) == 1
        assert "arc flash" in pages[0].text
        assert storage.exists(BUCKET, pages[0].image_storage_key or "")
        assert storage.exists(BUCKET, result.document.storage_key or "")

    def test_the_original_file_is_kept_byte_for_byte(
        self, db: Session, storage: InMemoryStorage, project: Project
    ) -> None:
        data = text_pdf([SPEC_SECTION_LINES])
        result = ingest_pdf(
            db,
            storage,
            project_id=project.id,
            doc_type=DocumentType.SPEC_SECTION,
            title="26 05 00",
            data=data,
            bucket=BUCKET,
        )
        assert storage.get(BUCKET, result.document.storage_key or "") == data

    def test_re_uploading_the_same_file_does_not_duplicate_it(
        self, db: Session, storage: InMemoryStorage, project: Project
    ) -> None:
        """A spec gets re-sent when somebody is unsure it landed."""
        data = text_pdf([SPEC_SECTION_LINES])
        kwargs = {
            "project_id": project.id,
            "doc_type": DocumentType.SPEC_SECTION,
            "title": "26 05 00",
            "data": data,
            "bucket": BUCKET,
        }

        first = ingest_pdf(db, storage, **kwargs)  # type: ignore[arg-type]
        second = ingest_pdf(db, storage, **kwargs)  # type: ignore[arg-type]

        assert second.already_ingested
        assert second.document.id == first.document.id
        assert db.query(SourceDocument).count() == 1
        assert db.query(DocumentPage).count() == 1

    def test_a_scan_is_stored_and_flagged_rather_than_rejected(
        self, db: Session, storage: InMemoryStorage, project: Project
    ) -> None:
        result = ingest_pdf(
            db,
            storage,
            project_id=project.id,
            doc_type=DocumentType.APPROVED_SUBMITTAL,
            title="Scanned submittal",
            data=imageless_scan_pdf(),
            bucket=BUCKET,
        )

        assert result.needs_a_person
        assert result.document.text_layer_status is TextLayerStatus.MISSING
        assert result.pages_ingested == 1, "the page image is still stored"

    def test_two_projects_can_ingest_the_same_file(
        self, db: Session, storage: InMemoryStorage, project: Project
    ) -> None:
        """Deduplication is per project; the same standard governs many jobs."""
        other = f.make_project(db, name="Another building")
        data = text_pdf([SPEC_SECTION_LINES])

        for owner in (project, other):
            ingest_pdf(
                db,
                storage,
                project_id=owner.id,
                doc_type=DocumentType.STANDARD,
                title="NFPA 70E extract",
                data=data,
                bucket=BUCKET,
            )

        assert db.query(SourceDocument).count() == 2


class TestSectionsFromAnIngestedDocument:
    def test_sections_come_back_with_their_clause_path(
        self, db: Session, storage: InMemoryStorage, project: Project
    ) -> None:
        result = ingest_pdf(
            db,
            storage,
            project_id=project.id,
            doc_type=DocumentType.SPEC_SECTION,
            title="26 05 00",
            data=text_pdf([SPEC_SECTION_LINES]),
            bucket=BUCKET,
        )

        sections = sections_for(db, result.document.id)

        assert [s.full_clause for s in sections] == [
            "26 05 00 - 1.7 - A",
            "26 05 00 - 1.7 - B",
        ]
        assert "FIELD QUALITY CONTROL" in sections[0].text, "the ancestors travel with it"


class TestStorage:
    def test_reading_something_that_was_never_written_is_an_error(
        self, storage: InMemoryStorage
    ) -> None:
        with pytest.raises(StorageError):
            storage.get(BUCKET, "nothing/here.png")
