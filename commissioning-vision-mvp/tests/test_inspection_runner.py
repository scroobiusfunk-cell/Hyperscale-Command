"""End-to-end tests for the checklist-driven inspection runner (synthetic frames only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.checklist import Checklist
from src.extract import NameplateReading
from src.inspection_runner import ItemStatus, run_checklist, run_item
from src.registry import Registry
from src.sim_frames import approach_sequence, bad_sequence
from src.voice import Phase

ROOT = Path(__file__).resolve().parent.parent
CHECKLIST = ROOT / "data" / "checklists" / "sample_electrical.json"


def rd(equip_id, fields):
    return NameplateReading(
        fields={k: v for k, (v, _) in fields.items()},
        confidence={k: c for k, (_, c) in fields.items()},
        evidence_photo=f"photos/{equip_id}.jpg", equip_id_tag=equip_id)


GOOD_MCCB = rd("EQ-MCCB-101", {"manufacturer": ("Square D", .97), "model": ("LJL36225", .95),
                               "voltage": ("480V", .95), "amp_rating": ("225", .95),
                               "aic_rating": ("65 kA", .95), "poles": ("3", .95)})
BAD_AIC_PNL = rd("EQ-PNL-201", {"manufacturer": ("Eaton", .97), "model": ("PRL2A", .95),
                                "voltage": ("480Y/277V", .95), "amp_rating": ("400", .95),
                                "aic_rating": ("22 kA", .95), "poles": ("3", .95)})
GOOD_XFMR = rd("EQ-XFMR-301", {"manufacturer": ("ABB", .96), "model": ("EE-DT3-500K", .95),
                               "voltage": ("480V", .95), "amp_rating": ("600", .95)})
BY_ITEM = {"CL-001": GOOD_MCCB, "CL-002": BAD_AIC_PNL, "CL-003": GOOD_XFMR}


@pytest.fixture(scope="module")
def setup():
    return Checklist.load_from_json(CHECKLIST), Registry.load()


def inject(frame, item):
    return BY_ITEM[item.id]


def test_checklist_loads_and_references_registry(setup):
    cl, reg = setup
    assert len(cl.items) == 3
    assert all(reg.get(i.equip_id) for i in cl.items)


def test_checklist_produces_report(setup):
    cl, reg = setup
    report = run_checklist(cl, {i.id: approach_sequence() for i in cl.items}, reg, inject)
    assert [r.status for r in report.results] == [
        ItemStatus.PASS, ItemStatus.DISCREPANCY, ItemStatus.PASS]
    assert report.summary == {"PASS": 2, "DISCREPANCY": 1, "NEEDS_REVIEW": 0,
                              "NO_CAPTURE": 0, "TOTAL": 3}
    md = report.to_markdown()
    assert "Inspector sign-off" in md and "DISCREPANC" in md and "CL-002" in md
    assert report.to_record()["summary"]["TOTAL"] == 3


def test_discrepancy_voice_names_aic(setup):
    cl, reg = setup
    r = run_item(cl.items[1], approach_sequence(), reg, inject)
    assert r.status == ItemStatus.DISCREPANCY
    assert "AIC rating" in r.voice[-1].text and "flagged" in r.voice[-1].text


def test_bad_frames_never_pass(setup):
    cl, reg = setup
    r = run_item(cl.items[0], bad_sequence(), reg, inject)
    assert r.status == ItemStatus.NO_CAPTURE
    assert r.reading is None and r.comparison is None
    assert "try again" in r.voice[-1].text.lower()


def test_missing_frames_is_no_capture(setup):
    cl, reg = setup
    report = run_checklist(cl, {}, reg, inject)
    assert all(r.status == ItemStatus.NO_CAPTURE for r in report.results)


def test_transcript_has_announce_and_result(setup):
    cl, reg = setup
    r = run_item(cl.items[0], approach_sequence(), reg, inject)
    phases = [p for p, _, _ in r.transcript]
    assert phases[0] == Phase.ANNOUNCE and phases[-1] == Phase.RESULT
    assert Phase.FRAMING in phases
    assert r.transcript[-1][1] == "Match, confirmed."


def test_expected_fields_override(setup):
    cl, reg = setup
    from dataclasses import replace
    item = replace(cl.items[0], expected_fields={"aic_rating": 100})
    r = run_item(item, approach_sequence(), reg, inject)
    assert r.status == ItemStatus.DISCREPANCY


def test_low_confidence_needs_review(setup):
    cl, reg = setup
    murky = rd("EQ-MCCB-101", {"manufacturer": ("Square D", .97), "model": ("LJL36225", .95),
                               "voltage": ("480V", .95), "amp_rating": ("225", .95),
                               "aic_rating": ("65 kA", .30), "poles": ("3", .95)})
    r = run_item(cl.items[0], approach_sequence(), reg, lambda f, i: murky)
    assert r.status == ItemStatus.NEEDS_REVIEW
    assert "flagged for review" in r.voice[-1].text
