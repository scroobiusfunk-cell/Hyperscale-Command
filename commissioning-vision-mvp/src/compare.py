"""Conservative comparison of a NameplateReading against the approved record.

Principle: this is decision SUPPORT. Only a clean, confident, field-by-field
MATCH yields PASS. Anything unreadable, missing, low-confidence, or ambiguous
yields NEEDS_REVIEW. A confident disagreement yields DISCREPANCY.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .extract import NameplateReading
from .registry import ApprovedItem

CONFIDENCE_THRESHOLD = 0.75

# Fields compared, in report order. Skipped when the approved value is None
# (e.g. a transformer has no AIC/poles).
COMPARED_FIELDS = ["manufacturer", "model", "voltage", "amp_rating", "aic_rating", "poles"]
# Safety-critical fields are highlighted in reports.
CRITICAL_FIELDS = {"voltage", "amp_rating", "aic_rating"}


class FieldStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    MISSING = "MISSING"
    UNVERIFIABLE = "UNVERIFIABLE"


class OverallStatus(str, Enum):
    PASS = "PASS"
    DISCREPANCY = "DISCREPANCY"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class FieldResult:
    name: str
    status: FieldStatus
    approved: Any
    observed_raw: Any
    confidence: Optional[float]
    reason: str
    critical: bool = False


@dataclass
class VerificationResult:
    equip_id: str
    overall: OverallStatus
    confidence: float                      # min confidence over compared fields (conservative)
    fields: list[FieldResult]
    evidence_photo: str
    submittal_ref: str = ""
    capture_id: str = ""
    captured_at: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- normalizers
# Each returns a canonical value, or None when the raw text cannot be parsed
# (=> UNVERIFIABLE, never a guess).

_MANUFACTURER_ALIASES = {
    "square d": {"square d", "sq d", "sqd", "squared", "square d company", "square d by schneider electric"},
    "eaton": {"eaton", "eaton corp", "eaton corporation", "cutler hammer", "eaton cutler hammer"},
    "abb": {"abb", "abb inc", "abb ltd"},
    "siemens": {"siemens", "siemens industry", "siemens industry inc"},
    "ge": {"ge", "general electric", "ge industrial"},
}
_ALIAS_LOOKUP = {a: canon for canon, names in _MANUFACTURER_ALIASES.items() for a in names}


def norm_manufacturer(raw: Any) -> Optional[str]:
    s = re.sub(r"[^a-z0-9 ]+", " ", str(raw).lower())
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return None
    return _ALIAS_LOOKUP.get(s, s)


def norm_model(raw: Any) -> Optional[str]:
    s = str(raw).upper()
    if "?" in s or "�" in s:        # garbled characters from OCR
        return None
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s or None


def norm_voltage(raw: Any) -> Optional[str]:
    """'480V' / '480' / '480 VAC' -> '480'; '480Y/277V' -> '480Y/277'."""
    s = str(raw).upper().replace(" ", "")
    s = re.sub(r"(VAC|VOLTS?|AC|V)", "", s)
    return s if re.fullmatch(r"\d+(\.\d+)?([YD]?/\d+(\.\d+)?)?[YD]?", s) else None


def _num(s: str) -> Optional[float]:
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def norm_amps(raw: Any) -> Optional[float]:
    m = re.fullmatch(r"\s*([\d.,]+)\s*(A|AMPS?|AMPERES?)?\s*", str(raw), re.I)
    return _num(m.group(1)) if m else None


def norm_aic_ka(raw: Any) -> Optional[float]:
    """'65kA' / '65 KAIC' / '65,000 A' / '65000' -> 65.0 (kA)."""
    m = re.fullmatch(r"\s*([\d.,]+)\s*(K\s*A\s*I?\s*C?|K\s*A\s*RMS|A\s*I\s*C|A|AMPS?)?\s*", str(raw), re.I)
    if not m:
        return None
    val = _num(m.group(1))
    if val is None:
        return None
    unit = (m.group(2) or "").upper().replace(" ", "")
    if unit.startswith("K"):
        return val
    if unit in ("A", "AMP", "AMPS") or (unit in ("", "AIC") and val >= 1000):
        return val / 1000.0
    return val  # bare small number or "AIC": assume kA


def norm_poles(raw: Any) -> Optional[int]:
    m = re.fullmatch(r"\s*(\d+)\s*(P|POLES?)?\s*", str(raw), re.I)
    return int(m.group(1)) if m else None


_NORMALIZERS: dict[str, Callable[[Any], Any]] = {
    "manufacturer": norm_manufacturer,
    "model": norm_model,
    "voltage": norm_voltage,
    "amp_rating": norm_amps,
    "aic_rating": norm_aic_ka,
    "poles": norm_poles,
}
_UNITS = {"amp_rating": "A", "aic_rating": " kA"}


# ------------------------------------------------------------------- compare
def _is_missing(v: Any) -> bool:
    return v is None or str(v).strip() == ""


def _compare_field(name: str, raw: Any, conf: Optional[float], approved: Any,
                   threshold: float) -> FieldResult:
    crit = name in CRITICAL_FIELDS
    unit = _UNITS.get(name, "")

    def res(status: FieldStatus, reason: str) -> FieldResult:
        return FieldResult(name, status, approved, raw, conf, reason, crit)

    if _is_missing(raw):
        return res(FieldStatus.MISSING, "Not found on nameplate reading.")

    norm = _NORMALIZERS[name]
    seen, want = norm(raw), norm(approved)
    if want is None:   # bad registry data must never pass silently
        return res(FieldStatus.UNVERIFIABLE, f"Approved value {approved!r} could not be normalized.")

    if conf is None or conf < threshold:
        c = "none" if conf is None else f"{conf:.2f}"
        return res(FieldStatus.UNVERIFIABLE,
                   f"Low confidence ({c} < {threshold:.2f}); read {raw!r}, approved {approved!r}. Re-capture or verify by eye.")

    if seen is None:
        return res(FieldStatus.UNVERIFIABLE, f"Could not parse reading {raw!r}; verify by eye.")

    if seen == want:
        return res(FieldStatus.MATCH, f"{raw!r} matches approved {approved!r} after normalization.")

    # Voltage: a bare '480' against an approved '480Y/277' is incomplete, not wrong.
    if name == "voltage" and isinstance(want, str) and want.startswith(seen) and want[len(seen)] in "YD/":
        return res(FieldStatus.UNVERIFIABLE,
                   f"Reading {raw!r} is only part of approved {approved!r}; confirm full rating.")

    shown = f"{seen:g}{unit}" if isinstance(seen, float) else str(seen)
    wshown = f"{want:g}{unit}" if isinstance(want, float) else str(want)
    return res(FieldStatus.MISMATCH, f"Observed {shown} but approved {wshown}.")


def compare(reading: NameplateReading, approved: ApprovedItem,
            threshold: float = CONFIDENCE_THRESHOLD) -> VerificationResult:
    results: list[FieldResult] = []
    for name in COMPARED_FIELDS:
        want = getattr(approved, name)
        if want is None:
            continue   # not applicable for this equipment type
        results.append(_compare_field(name, reading.fields.get(name),
                                      reading.confidence.get(name), want, threshold))

    warnings: list[str] = []
    if reading.equip_id_tag and reading.equip_id_tag != approved.equip_id:
        warnings.append(f"Capture tagged {reading.equip_id_tag!r} but compared against {approved.equip_id!r}.")
    if not results:
        warnings.append("No comparable fields.")

    statuses = {r.status for r in results}
    if FieldStatus.MISMATCH in statuses:
        overall = OverallStatus.DISCREPANCY
    elif statuses == {FieldStatus.MATCH} and not warnings:
        overall = OverallStatus.PASS
    else:   # MISSING / UNVERIFIABLE / warnings / nothing compared -> a human decides
        overall = OverallStatus.NEEDS_REVIEW

    confs = [r.confidence or 0.0 for r in results]
    return VerificationResult(
        equip_id=approved.equip_id,
        overall=overall,
        confidence=min(confs) if confs else 0.0,
        fields=results,
        evidence_photo=reading.evidence_photo,
        submittal_ref=approved.submittal_ref,
        capture_id=reading.capture_id,
        captured_at=reading.captured_at,
        warnings=warnings,
    )
