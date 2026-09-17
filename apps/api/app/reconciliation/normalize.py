"""Tag normalization.

The same switchboard is "SWBD-101" in the schedule, "SWBD 101" in CxAlloy,
"swbd101" in a submittal, and "DC07-SWBD-101" on the nameplate. Normalization
reduces those to something comparable without throwing away what the source
actually said — the raw value is always stored alongside.

Every function here is pure, so the matcher's behaviour can be reasoned about
from these rules alone.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Characters used as separators in equipment tags across the sources we see.
_SEPARATORS = re.compile(r"[\s\-_./\\|:]+")
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def normalize_tag(raw: str) -> str:
    """Case, whitespace and separator normalization, keeping segment structure.

    "  swbd 101 " -> "SWBD-101"
    "SWBD__101"   -> "SWBD-101"
    "swbd/101a"   -> "SWBD-101A"
    """
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.strip().upper()
    text = _SEPARATORS.sub("-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def canonical_key(raw: str) -> str:
    """Separator-free form, for comparing tags that disagree only about punctuation.

    "SWBD-101" and "SWBD 101" and "swbd101" all produce "SWBD101".
    """
    return _NON_ALNUM.sub("", normalize_tag(raw))


def segments(raw: str) -> list[str]:
    """The normalized tag split on separators. "DC07-SWBD-101" -> [DC07, SWBD, 101]."""
    normalized = normalize_tag(raw)
    return [segment for segment in normalized.split("-") if segment]


def strip_prefixes(raw: str, prefixes: frozenset[str]) -> str:
    """Remove leading project or discipline prefixes.

    Only whole leading segments are removed, so stripping "DC07" from
    "DC07-SWBD-101" gives "SWBD-101" while "DC071-SWBD" is left alone. Removal
    repeats, because tags carry more than one prefix often enough to matter, and
    it never strips the final segment: a tag is not allowed to normalize to
    nothing.
    """
    if not prefixes:
        return normalize_tag(raw)

    normalized_prefixes = {normalize_tag(p) for p in prefixes}
    parts = segments(raw)
    while len(parts) > 1 and parts[0] in normalized_prefixes:
        parts = parts[1:]
    return "-".join(parts)


def tag_similarity(left: str, right: str) -> float:
    """0 to 1 similarity between two tags, compared on their canonical keys.

    Exact canonical equality is 1.0, which is the only score the matcher treats
    as certain. Everything else is a ratio and lands in the queue unless other
    signals agree.
    """
    left_key, right_key = canonical_key(left), canonical_key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()
