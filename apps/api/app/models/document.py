"""Source documents.

Requirement.source points at a document, clause and page, so requirements
cannot be stored without somewhere for doc_id to reference. Only the fields the
Requirement record needs are here; ingestion adds page images and extracted
text in its own change.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DocumentType, TextLayerStatus


class SourceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_document"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="RESTRICT"), nullable=False
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        pg_enum(DocumentType, "document_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="sha256 of the uploaded bytes. Re-uploading the same file is a no-op.",
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_layer_status: Mapped[TextLayerStatus | None] = mapped_column(
        pg_enum(TextLayerStatus, "text_layer_status"),
        nullable=True,
        comment=(
            "A document without a text layer is flagged for a person, never silently "
            "OCR'd and never silently dropped. See docs/OPEN_QUESTIONS.md Q2."
        ),
    )
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
