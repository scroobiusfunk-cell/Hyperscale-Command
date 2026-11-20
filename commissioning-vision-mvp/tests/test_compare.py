import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.compare import (FieldStatus, OverallStatus, compare, norm_aic_ka,
                         norm_manufacturer, norm_voltage)
from src.extract import MockExtractor, NameplateReading
from src.registry import Registry

REG = Registry.load()
BREAKER = REG.get("EQ-MCCB-101")
CAPTURES = Path(__file__).resolve().parent.parent / "data" / "captures"


def reading(**overrides):
    vals = {"manufacturer": "Square D", "model": "LJL36225", "voltage": "480V",
            "amp_rating": "225A", "aic_rating": "65kA", "poles": "3"}
    vals.update(overrides)
    return NameplateReading(fields=vals, confidence={k: 0.95 for k in vals}, evidence_photo="x.jpg")


def status_of(result, name):
    return next(f.status for f in result.fields if f.name == name)


def test_clean_pass():
    r = compare(reading(), BREAKER)
    assert r.overall == OverallStatus.PASS
    assert all(f.status == FieldStatus.MATCH for f in r.fields)


def test_safety_critical_mismatch_is_discrepancy():
    r = compare(reading(aic_rating="22 kA"), BREAKER)
    assert r.overall == OverallStatus.DISCREPANCY
    assert status_of(r, "aic_rating") == FieldStatus.MISMATCH


def test_low_confidence_is_review_not_pass():
    rd = reading()
    rd.confidence["amp_rating"] = 0.50   # value matches, but we cannot trust the read
    r = compare(rd, BREAKER)
    assert r.overall == OverallStatus.NEEDS_REVIEW
    assert status_of(r, "amp_rating") == FieldStatus.UNVERIFIABLE


def test_missing_field_is_review():
    rd = reading()
    rd.fields["poles"] = None
    r = compare(rd, BREAKER)
    assert r.overall == OverallStatus.NEEDS_REVIEW
    assert status_of(r, "poles") == FieldStatus.MISSING


def test_mismatch_outranks_review():
    r = compare(reading(aic_rating="22kA", poles=None), BREAKER)
    assert r.overall == OverallStatus.DISCREPANCY


def test_voltage_normalization():
    assert norm_voltage("480V") == norm_voltage("480") == norm_voltage("480 VAC") == "480"
    r = compare(reading(voltage="480 VAC"), BREAKER)
    assert status_of(r, "voltage") == FieldStatus.MATCH


def test_voltage_partial_is_not_pass():
    r = compare(reading(voltage="480"), REG.get("EQ-PNL-201"))   # approved 480Y/277V
    assert status_of(r, "voltage") == FieldStatus.UNVERIFIABLE


def test_manufacturer_alias():
    assert norm_manufacturer("Sq D") == norm_manufacturer(" SQUARE  D ") == "square d"
    r = compare(reading(manufacturer="Sq D"), BREAKER)
    assert status_of(r, "manufacturer") == FieldStatus.MATCH


def test_aic_units():
    assert norm_aic_ka("65,000 A") == norm_aic_ka("65 kA") == 65.0


def test_unparseable_value_is_unverifiable():
    r = compare(reading(amp_rating="2?5A"), BREAKER)
    assert status_of(r, "amp_rating") == FieldStatus.UNVERIFIABLE
    assert r.overall == OverallStatus.NEEDS_REVIEW


def test_tag_mismatch_never_passes():
    rd = reading()
    rd.equip_id_tag = "EQ-PNL-201"
    assert compare(rd, BREAKER).overall == OverallStatus.NEEDS_REVIEW


def test_sample_captures_end_to_end():
    expected = {"capture_pass.json": OverallStatus.PASS,
                "capture_discrepancy.json": OverallStatus.DISCREPANCY,
                "capture_review.json": OverallStatus.NEEDS_REVIEW}
    for name, want in expected.items():
        rd = MockExtractor().extract(CAPTURES / name)
        assert compare(rd, REG.get(rd.equip_id_tag)).overall == want
