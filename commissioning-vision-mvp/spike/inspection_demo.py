"""Full MOCK inspection over the sample checklist (no photos, no hardware).

Run from the project dir:  python spike/inspection_demo.py
Frames are simulated; nameplate readings are injected (stand-in for OCR).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.checklist import Checklist
from src.extract import NameplateReading
from src.inspection_runner import run_checklist
from src.registry import Registry
from src.sim_frames import approach_sequence

ROOT = Path(__file__).resolve().parent.parent


def reading(equip_id, cap, fields):
    return NameplateReading(
        fields={k: v for k, (v, _) in fields.items()},
        confidence={k: c for k, (_, c) in fields.items()},
        evidence_photo=f"photos/{cap}_nameplate.jpg", equip_id_tag=equip_id,
        capture_id=cap, captured_at="2026-11-20T15:00:00Z")


READINGS = {
    # CL-001: clean PASS
    "CL-001": reading("EQ-MCCB-101", "CAP-1001", {
        "manufacturer": ("Sq D", .97), "model": ("LJL36225", .93), "voltage": ("480 VAC", .95),
        "amp_rating": ("225 A", .96), "aic_rating": ("65 kA", .91), "poles": ("3P", .94)}),
    # CL-002: AIC 22 kA read vs 65 kA approved -> DISCREPANCY
    "CL-002": reading("EQ-PNL-201", "CAP-1002", {
        "manufacturer": ("Eaton", .98), "model": ("PRL2A", .90), "voltage": ("480Y/277V", .92),
        "amp_rating": ("400A", .95), "aic_rating": ("22 kA", .94), "poles": ("3", .88)}),
    # CL-003: transformer, no AIC/poles applicable -> PASS
    "CL-003": reading("EQ-XFMR-301", "CAP-1003", {
        "manufacturer": ("ABB", .96), "model": ("EE-DT3-500K", .92), "voltage": ("480V", .94),
        "amp_rating": ("600 A", .93)}),
}


def main():
    checklist = Checklist.load_from_json(ROOT / "data" / "checklists" / "sample_electrical.json")
    registry = Registry.load()
    sources = {it.id: approach_sequence() for it in checklist.items}
    report = run_checklist(checklist, sources, registry, lambda frame, item: READINGS[item.id])

    print(f"=== {checklist.name} ({len(checklist.items)} items) ===")
    for r in report.results:
        print(f"\n--- {r.item.id} [{r.item.equip_id}] profile={r.item.profile_key} ---")
        print("Voice transcript:")
        for phase, text, cue in r.transcript:
            print(f"  [{phase.value:<8}] {text}   (cue: {getattr(cue, 'name', '-')})")
        print("Gate transitions:")
        for idx, state, cue in r.gate_trace:
            print(f"  frame {idx}: {state.name} / {cue.name}")
        print(f"Result: {r.status.value}  evidence={r.evidence_ref}")

    print("\n=== Summary ===")
    print(report.summary)
    print("\n=== Report (markdown) ===\n")
    print(report.to_markdown())


if __name__ == "__main__":
    main()
