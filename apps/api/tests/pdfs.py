"""Building PDFs for tests.

Real files rather than mocks: the point of these tests is that a PDF goes in and
usable text comes out, and a mocked reader would prove nothing about that.
"""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


def text_pdf(pages: list[list[str]]) -> bytes:
    """A PDF with a text layer. One list of lines per page."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    for lines in pages:
        y = 720
        for line in lines:
            pdf.drawString(72, y, line)
            y -= 14
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def imageless_scan_pdf(page_count: int = 1) -> bytes:
    """A PDF with no text layer at all, standing in for a scanned submittal."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    for _ in range(page_count):
        # Lines and boxes only: something is on the page, none of it is text.
        pdf.rect(72, 600, 400, 120, stroke=1, fill=0)
        pdf.line(72, 580, 472, 580)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


SPEC_SECTION_LINES = [
    "26 05 00 COMMON WORK RESULTS FOR ELECTRICAL",
    "",
    "1.7 FIELD QUALITY CONTROL",
    "",
    "A. Each switchboard shall bear an arc flash warning label on the front cover.",
    "",
    "B. Provide a typewritten nameplate for each panelboard showing the panel tag.",
]
