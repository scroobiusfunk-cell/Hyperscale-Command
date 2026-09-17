"""Source documents.

Requirement.source points at a document, clause and page, so requirements
cannot be stored without somewhere for doc_id to reference. Only the fields the
Requirement record needs are here; ingestion adds page images and extracted
text in its own change.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import pg_enum
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DocumentType


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
