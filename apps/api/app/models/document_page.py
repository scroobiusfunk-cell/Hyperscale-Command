"""One page of an ingested document.

The architecture doc requires the page image to be stored alongside the text so
every requirement can show a curator its source. Text lives in Postgres because
the section splitter and extraction read it constantly; the image lives in
object storage because it is large and only read when someone opens a clause.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DocumentPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_page"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_document.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="1-indexed, as a person reading the document would say."
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
