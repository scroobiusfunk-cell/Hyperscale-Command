"""Splitting document text into clause sections.

Extraction runs one model call per section, so the split decides what the model
sees together. Getting it wrong in one direction buries a requirement in a wall
of text; in the other it hands the model a fragment with no context — "A. Each
switchboard shall bear a label" means something different under FIELD QUALITY
CONTROL than under SUBMITTALS.

So headings are tracked as a stack rather than a flat list, and every section
carries its ancestors' heading lines with it. A heading with no body of its own
becomes context for what is under it instead of a section nobody can act on.

Deterministic and regex-based. Construction specs are more regular than most
prose: CSI section numbers, numbered articles, lettered paragraphs. Anything the
splitter does not recognise stays attached to the clause above it rather than
being dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: A CSI MasterFormat section number: "26 05 00", sometimes "26 05 00.13".
CSI_SECTION = re.compile(r"^\s{0,8}(\d{2}\s\d{2}\s\d{2}(?:\.\d{2})?)\b\s*(.*)$")

#: A numbered article or paragraph: "1.7", "2.1.A", "3.04".
NUMBERED_CLAUSE = re.compile(r"^\s{0,8}(\d{1,2}(?:\.\d{1,3})+(?:\.[A-Z])?)\s+(\S.*)$")

#: A lettered paragraph: "A. Provide...", "B) Provide..."
LETTERED_CLAUSE = re.compile(r"^\s{0,8}([A-Z])[.)]\s+(\S.*)$")

#: Depth in the heading stack. A lettered paragraph always sits below a numbered
#: one, which always sits below a CSI section number.
CSI_LEVEL = 0
LETTERED_LEVEL = 9

#: Body shorter than this is folded into the section before it: a stub is not
#: worth a model call of its own.
MIN_SECTION_CHARS = 40


@dataclass(frozen=True)
class Heading:
    level: int
    clause: str
    line: str
    remainder: str
    """Whatever followed the clause number on the same line."""

    @property
    def is_title_only(self) -> bool:
        """Whether this heading is a title rather than a requirement in itself.

        Spec titles are conventionally upper case — "FIELD QUALITY CONTROL",
        "PRODUCTS" — while requirement prose is sentence case. A title-only
        heading becomes context for what sits under it rather than a section of
        its own, because on its own there is nothing in it to check.

        A lettered paragraph carries its whole requirement on the heading line,
        so this is what stops those being thrown away.
        """
        if not self.remainder.strip():
            return True
        letters = [c for c in self.remainder if c.isalpha()]
        return bool(letters) and all(c.isupper() for c in letters)


@dataclass(frozen=True)
class DocumentSection:
    """One clause and its body, ready for a single extraction call."""

    clause: str
    page_number: int
    text: str
    clause_path: tuple[str, ...] = ()
    """Enclosing clauses, outermost first. `26 05 00`, `1.7`, `A`."""

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def full_clause(self) -> str:
        """How a person would cite it: '26 05 00 - 1.7.A'."""
        return " - ".join(self.clause_path) if self.clause_path else self.clause


def _match_heading(line: str) -> Heading | None:
    csi = CSI_SECTION.match(line)
    if csi:
        return Heading(
            level=CSI_LEVEL, clause=csi.group(1), line=line.strip(), remainder=csi.group(2)
        )

    numbered = NUMBERED_CLAUSE.match(line)
    if numbered:
        clause = numbered.group(1)
        # "1.7" sits above "1.7.2", which sits above "1.7.2.A".
        return Heading(
            level=clause.count("."),
            clause=clause,
            line=line.strip(),
            remainder=numbered.group(2),
        )

    lettered = LETTERED_CLAUSE.match(line)
    if lettered:
        return Heading(
            level=LETTERED_LEVEL,
            clause=lettered.group(1),
            line=line.strip(),
            remainder=lettered.group(2),
        )

    return None


@dataclass
class _Open:
    stack: list[Heading] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    page_number: int = 1

    def flush(self) -> DocumentSection | None:
        if not self.stack:
            return None

        leaf = self.stack[-1]
        body = "\n".join(self.body).strip()
        if not body and leaf.is_title_only:
            # Pure context. The stack already carries it into whatever sits
            # under it, so emitting it on its own would only add a section with
            # nothing in it to check.
            return None

        # Ancestors give the leaf its meaning; the leaf's own line carries the
        # requirement when it is a lettered paragraph.
        lines = [h.line for h in self.stack if h.line]
        if body:
            lines.append(body)
        return DocumentSection(
            clause=leaf.clause,
            page_number=self.page_number,
            text="\n".join(lines).strip(),
            clause_path=tuple(h.clause for h in self.stack),
        )


def split_into_sections(
    pages: list[tuple[int, str]], *, fallback_clause: str = "(unnumbered)"
) -> list[DocumentSection]:
    """Split (page_number, text) pairs into clause sections.

    Text before the first recognised clause is kept under `fallback_clause`
    rather than discarded: a specification that opens with an unnumbered
    paragraph still states requirements.
    """
    sections: list[DocumentSection] = []
    open_section = _Open()

    def flush() -> None:
        section = open_section.flush()
        if section is not None:
            sections.append(section)
        open_section.body = []

    for page_number, page_text in pages:
        for raw_line in page_text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                if open_section.body:
                    open_section.body.append("")
                continue

            heading = _match_heading(line)
            if heading is None:
                if not open_section.stack:
                    open_section.stack = [
                        Heading(level=CSI_LEVEL, clause=fallback_clause, line="", remainder="")
                    ]
                    open_section.page_number = page_number
                if not open_section.body:
                    open_section.page_number = page_number
                open_section.body.append(line)
                continue

            flush()
            while open_section.stack and open_section.stack[-1].level >= heading.level:
                open_section.stack.pop()
            open_section.stack.append(heading)
            open_section.page_number = page_number

    flush()
    return _fold_short_sections(sections)


def _fold_short_sections(sections: list[DocumentSection]) -> list[DocumentSection]:
    """Attach a stub of a section to the one before it."""
    folded: list[DocumentSection] = []
    for section in sections:
        if not section.text:
            continue
        if folded and section.char_count < MIN_SECTION_CHARS:
            previous = folded[-1]
            folded[-1] = DocumentSection(
                clause=previous.clause,
                page_number=previous.page_number,
                text=f"{previous.text}\n{section.text}",
                clause_path=previous.clause_path,
            )
        else:
            folded.append(section)
    return folded
