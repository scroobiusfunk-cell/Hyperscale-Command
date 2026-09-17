"""Tag normalization. No database: these are the rules everything else rests on."""

from __future__ import annotations

import pytest

from app.reconciliation.normalize import (
    canonical_key,
    normalize_tag,
    segments,
    strip_prefixes,
    tag_similarity,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SWBD-101", "SWBD-101"),
        ("  swbd 101 ", "SWBD-101"),
        ("SWBD__101", "SWBD-101"),
        ("swbd/101", "SWBD-101"),
        ("SWBD.101", "SWBD-101"),
        ("SWBD\\101", "SWBD-101"),
        ("SWBD:101", "SWBD-101"),
        ("SWBD---101", "SWBD-101"),
        ("-SWBD-101-", "SWBD-101"),
        ("swbd101a", "SWBD101A"),
    ],
)
def test_normalize_tag(raw: str, expected: str) -> None:
    assert normalize_tag(raw) == expected


def test_normalize_strips_accents() -> None:
    """Rare in tags, but a pasted spreadsheet cell can carry them.

    The two spellings of E-acute (precomposed and E plus a combining accent)
    look identical and compare unequal, so both have to land on the same tag.
    """
    precomposed = "PAN\u00c9L-1"
    decomposed = "PANE\u0301L-1"
    assert precomposed != decomposed
    assert normalize_tag(precomposed) == "PANEL-1"
    assert normalize_tag(decomposed) == "PANEL-1"


@pytest.mark.parametrize(
    "variant", ["SWBD-101", "SWBD 101", "swbd101", "SWBD_101", " swbd - 101 ", "SWBD/101"]
)
def test_all_punctuation_variants_share_a_canonical_key(variant: str) -> None:
    assert canonical_key(variant) == "SWBD101"


def test_canonical_key_keeps_genuinely_different_tags_apart() -> None:
    assert canonical_key("SWBD-101") != canonical_key("SWBD-102")
    assert canonical_key("SWBD-101") != canonical_key("SWBD-101A")


def test_segments_splits_on_separators() -> None:
    assert segments("DC07-SWBD-101") == ["DC07", "SWBD", "101"]
    assert segments("swbd 101") == ["SWBD", "101"]


class TestStripPrefixes:
    prefixes = frozenset({"DC07", "E"})

    def test_removes_a_leading_project_prefix(self) -> None:
        assert strip_prefixes("DC07-SWBD-101", self.prefixes) == "SWBD-101"

    def test_removes_several_leading_prefixes(self) -> None:
        assert strip_prefixes("DC07-E-SWBD-101", self.prefixes) == "SWBD-101"

    def test_only_removes_whole_segments(self) -> None:
        """DC071 is not the DC07 prefix, and treating it as one loses a real tag."""
        assert strip_prefixes("DC071-SWBD-101", self.prefixes) == "DC071-SWBD-101"

    def test_never_strips_a_tag_to_nothing(self) -> None:
        assert strip_prefixes("DC07", self.prefixes) == "DC07"

    def test_does_not_remove_a_prefix_from_the_middle(self) -> None:
        assert strip_prefixes("SWBD-DC07-101", self.prefixes) == "SWBD-DC07-101"

    def test_no_prefixes_configured_is_plain_normalization(self) -> None:
        assert strip_prefixes("dc07 swbd 101", frozenset()) == "DC07-SWBD-101"


class TestTagSimilarity:
    def test_punctuation_differences_score_exactly_one(self) -> None:
        assert tag_similarity("SWBD-101", "swbd 101") == 1.0

    def test_different_tags_score_below_one(self) -> None:
        assert tag_similarity("SWBD-101", "SWBD-102") < 1.0

    def test_unrelated_tags_score_low(self) -> None:
        assert tag_similarity("SWBD-101", "AHU-7") < 0.5

    def test_empty_input_scores_zero_rather_than_matching_everything(self) -> None:
        assert tag_similarity("", "SWBD-101") == 0.0
        assert tag_similarity("---", "SWBD-101") == 0.0
