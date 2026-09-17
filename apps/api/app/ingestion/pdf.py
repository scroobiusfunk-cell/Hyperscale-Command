"""Reading a PDF into page text and page images.

Two rules from the architecture doc and OPEN_QUESTIONS Q2:

- The page image is stored alongside the text, because every requirement has to
  be able to show a curator its source.
- A document without a text layer is *flagged*, not silently OCR'd and not
  silently dropped. Phase 1 has no OCR; a scanned submittal is a thing a person
  needs to know about, not a thing to guess at.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pypdfium2 as pdfium

from app.models.enums import TextLayerStatus

#: Below this many characters, a page is treated as having no usable text. A
#: scanned page still yields the odd stray glyph, and a genuinely blank page in
#: a real spec is common, so the threshold is about "is there prose here".
MIN_CHARS_FOR_TEXT_LAYER = 40

#: A document counts as having a text layer when at least this share of its
#: non-blank pages do. Specs routinely carry a scanned signature page or a
#: drawing extract without failing the whole document.
MIN_TEXT_PAGE_RATIO = 0.5

#: 2.0 is about 150 DPI at US Letter, which is legible for a curator reading a
#: clause on screen without making a 600-page spec unreasonable to store.
DEFAULT_RENDER_SCALE = 2.0


class PdfReadError(RuntimeError):
    """The file could not be read as a PDF."""


@dataclass(frozen=True)
class PdfPage:
    page_number: int
    """1-indexed, matching what a person reading the document would say."""
    text: str
    image_png: bytes

    @property
    def has_text(self) -> bool:
        return len(self.text.strip()) >= MIN_CHARS_FOR_TEXT_LAYER


@dataclass(frozen=True)
class ReadPdf:
    pages: tuple[PdfPage, ...]
    text_layer_status: TextLayerStatus

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def is_readable(self) -> bool:
        """Whether extraction can run at all, or a person has to intervene first."""
        return self.text_layer_status is not TextLayerStatus.MISSING


def _classify_text_layer(pages: list[PdfPage]) -> TextLayerStatus:
    if not pages:
        return TextLayerStatus.MISSING

    with_text = sum(1 for page in pages if page.has_text)
    if with_text == 0:
        return TextLayerStatus.MISSING
    if with_text == len(pages):
        return TextLayerStatus.PRESENT
    if with_text / len(pages) >= MIN_TEXT_PAGE_RATIO:
        return TextLayerStatus.PARTIAL
    return TextLayerStatus.MISSING


def read_pdf(data: bytes, *, render_scale: float = DEFAULT_RENDER_SCALE) -> ReadPdf:
    """Extract text and render a page image for every page.

    Raises `PdfReadError` for anything that is not a readable PDF. It never
    returns a partial document: a half-read spec would silently drop
    requirements, which is the failure this whole subsystem exists to avoid.
    """
    if not data:
        raise PdfReadError("The file was empty.")

    try:
        document = pdfium.PdfDocument(data)
    except Exception as exc:
        raise PdfReadError(f"Could not open the file as a PDF: {exc}") from exc

    pages: list[PdfPage] = []
    try:
        for index in range(len(document)):
            page = document[index]
            text = page.get_textpage().get_text_range() or ""
            image = page.render(scale=render_scale).to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pages.append(PdfPage(page_number=index + 1, text=text, image_png=buffer.getvalue()))
    except Exception as exc:
        raise PdfReadError(f"Failed while reading page {len(pages) + 1}: {exc}") from exc
    finally:
        document.close()

    if not pages:
        raise PdfReadError("The PDF has no pages.")

    return ReadPdf(pages=tuple(pages), text_layer_status=_classify_text_layer(pages))
