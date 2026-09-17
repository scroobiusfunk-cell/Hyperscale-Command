"""Ingesting a document: PDF in, pages and page images out.

Re-uploading the same file is a no-op rather than a second document. A
specification gets re-sent when someone is not sure it landed, and a duplicate
would double every requirement extracted from it.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.pdf import DEFAULT_RENDER_SCALE, PdfReadError, read_pdf
from app.ingestion.sections import DocumentSection, split_into_sections
from app.logging import get_logger
from app.models import DocumentPage, SourceDocument
from app.models.enums import DocumentType, TextLayerStatus
from app.storage import ObjectStorage

log = get_logger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    document: SourceDocument
    pages_ingested: int
    already_ingested: bool = False

    @property
    def needs_a_person(self) -> bool:
        """A document extraction cannot run on until somebody deals with it."""
        return self.document.text_layer_status is TextLayerStatus.MISSING


def _document_prefix(project_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"projects/{project_id}/documents/{document_id}"


def ingest_pdf(
    session: Session,
    storage: ObjectStorage,
    *,
    project_id: uuid.UUID,
    doc_type: DocumentType,
    title: str,
    data: bytes,
    bucket: str,
    render_scale: float = DEFAULT_RENDER_SCALE,
) -> IngestionResult:
    """Read a PDF into pages, store the original and the page images.

    Raises `PdfReadError` if the file cannot be read. A document with no text
    layer is stored and flagged rather than rejected: the page images are still
    worth having, and a person needs to see that the file arrived.
    """
    content_hash = hashlib.sha256(data).hexdigest()

    existing = session.execute(
        select(SourceDocument).where(
            SourceDocument.project_id == project_id,
            SourceDocument.content_hash == content_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        log.info(
            "ingestion.already_ingested",
            document_id=str(existing.id),
            content_hash=content_hash,
        )
        return IngestionResult(
            document=existing,
            pages_ingested=existing.page_count or 0,
            already_ingested=True,
        )

    parsed = read_pdf(data, render_scale=render_scale)

    document = SourceDocument(
        project_id=project_id,
        doc_type=doc_type,
        title=title,
        content_hash=content_hash,
        page_count=parsed.page_count,
        text_layer_status=parsed.text_layer_status,
        ingested_at=datetime.now(UTC),
    )
    session.add(document)
    session.flush()

    prefix = _document_prefix(project_id, document.id)
    document.storage_key = storage.put(bucket, f"{prefix}/original.pdf", data, "application/pdf")

    for page in parsed.pages:
        image_key = storage.put(
            bucket, f"{prefix}/pages/{page.page_number:04d}.png", page.image_png, "image/png"
        )
        session.add(
            DocumentPage(
                document_id=document.id,
                page_number=page.page_number,
                text=page.text,
                char_count=len(page.text),
                image_storage_key=image_key,
            )
        )

    session.flush()

    log.info(
        "ingestion.completed",
        document_id=str(document.id),
        doc_type=doc_type.value,
        pages=parsed.page_count,
        text_layer_status=parsed.text_layer_status.value,
    )
    return IngestionResult(document=document, pages_ingested=parsed.page_count)


def sections_for(session: Session, document_id: uuid.UUID) -> list[DocumentSection]:
    """The document's clause sections, in page order."""
    pages = (
        session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        )
        .scalars()
        .all()
    )
    return split_into_sections([(page.page_number, page.text) for page in pages])


__all__ = [
    "IngestionResult",
    "PdfReadError",
    "ingest_pdf",
    "sections_for",
]
