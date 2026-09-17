"""The section splitter. No database, no PDF — just the rules."""

from __future__ import annotations

from app.ingestion.sections import DocumentSection, split_into_sections


def split(text: str, page: int = 1) -> list[DocumentSection]:
    return split_into_sections([(page, text)])


class TestClauseRecognition:
    def test_a_csi_section_number_opens_a_document(self) -> None:
        sections = split(
            "26 05 00 COMMON WORK RESULTS\n\n"
            "A. Each switchboard shall bear an arc flash warning label on the cover."
        )
        assert sections[0].clause_path[0] == "26 05 00"

    def test_numbered_and_lettered_clauses_nest(self) -> None:
        sections = split(
            "26 05 00 ELECTRICAL\n"
            "1.7 FIELD QUALITY CONTROL\n"
            "A. Each switchboard shall bear an arc flash warning label on the cover."
        )
        assert sections[0].clause_path == ("26 05 00", "1.7", "A")
        assert sections[0].full_clause == "26 05 00 - 1.7 - A"

    def test_a_deeper_number_nests_under_a_shallower_one(self) -> None:
        sections = split(
            "1.7 FIELD QUALITY CONTROL\n"
            "1.7.2 TESTING\n"
            "A. Test every protective device and record the settings on the form."
        )
        assert sections[0].clause_path == ("1.7", "1.7.2", "A")

    def test_a_sibling_clause_replaces_rather_than_nests(self) -> None:
        sections = split(
            "26 05 00 ELECTRICAL\n"
            "1.7 FIELD QUALITY CONTROL\n"
            "A. Each switchboard shall bear an arc flash warning label on the cover.\n"
            "2.1 PRODUCTS\n"
            "A. Panelboards shall be as scheduled on the drawings and approved."
        )
        assert [s.clause_path for s in sections] == [
            ("26 05 00", "1.7", "A"),
            ("26 05 00", "2.1", "A"),
        ]

    def test_a_lettered_clause_may_use_a_bracket(self) -> None:
        sections = split("1.7 QUALITY\nB) Provide a typewritten nameplate for every panelboard.")
        assert sections[0].clause_path == ("1.7", "B")


class TestContextTravelsWithTheSection:
    def test_ancestor_headings_are_included_in_the_text(self) -> None:
        """ "A. Each switchboard shall bear a label" means something different
        under FIELD QUALITY CONTROL than under SUBMITTALS."""
        sections = split(
            "26 05 00 COMMON WORK RESULTS\n"
            "1.7 FIELD QUALITY CONTROL\n"
            "A. Each switchboard shall bear an arc flash warning label on the cover."
        )
        text = sections[0].text
        assert "COMMON WORK RESULTS" in text
        assert "FIELD QUALITY CONTROL" in text
        assert "arc flash" in text

    def test_a_title_only_heading_is_context_not_a_section(self) -> None:
        sections = split(
            "26 05 00 ELECTRICAL\n"
            "1.7 FIELD QUALITY CONTROL\n"
            "A. Each switchboard shall bear an arc flash warning label on the cover."
        )
        assert len(sections) == 1, "only the paragraph with something to check"

    def test_continuation_lines_stay_with_their_clause(self) -> None:
        sections = split(
            "1.7 QUALITY\n"
            "A. Each switchboard shall bear an arc flash warning label.\n"
            "   The label shall be legible from standing position."
        )
        assert len(sections) == 1
        assert "legible from standing position" in sections[0].text


class TestNothingIsDropped:
    def test_text_before_any_clause_is_kept(self) -> None:
        """A spec that opens with an unnumbered paragraph still states requirements."""
        sections = split(
            "This section covers arc flash labelling for all distribution equipment.\n"
            "26 05 00 ELECTRICAL\n"
            "A. Each switchboard shall bear an arc flash warning label on the cover."
        )
        assert sections[0].clause_path[0] == "(unnumbered)"
        assert "arc flash labelling" in sections[0].text

    def test_a_stub_section_is_folded_into_the_one_before_it(self) -> None:
        sections = split(
            "1.7 QUALITY\n"
            "A. Each switchboard shall bear an arc flash warning label on the cover.\n"
            "B. See above."
        )
        assert len(sections) == 1
        assert "See above." in sections[0].text

    def test_empty_input_produces_no_sections_rather_than_failing(self) -> None:
        assert split("") == []
        assert split_into_sections([]) == []

    def test_page_numbers_follow_the_text(self) -> None:
        sections = split_into_sections(
            [
                (11, "1.7 QUALITY\nA. Each switchboard shall bear an arc flash label here."),
                (12, "2.1 PRODUCTS\nA. Panelboards shall be as scheduled on the drawings."),
            ]
        )
        assert [s.page_number for s in sections] == [11, 12]
