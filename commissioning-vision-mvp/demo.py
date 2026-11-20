"""End-to-end offline demo: capture sidecars -> extract -> compare -> report."""
import json
from pathlib import Path

from src.compare import compare
from src.extract import MockExtractor
from src.registry import Registry
from src.report import to_markdown, to_record

ROOT = Path(__file__).resolve().parent
CAPTURES = ["capture_pass.json", "capture_discrepancy.json", "capture_review.json"]


def main() -> None:
    registry = Registry.load()
    extractor = MockExtractor()   # swap for VisionExtractor once a real API is wired in
    out = ROOT / "out"
    out.mkdir(exist_ok=True)

    rows = []
    for name in CAPTURES:
        reading = extractor.extract(ROOT / "data" / "captures" / name)
        approved = registry.get(reading.equip_id_tag or "")
        if approved is None:
            rows.append((name, reading.equip_id_tag, "NEEDS_REVIEW", 0.0, "unknown equip_id"))
            continue
        result = compare(reading, approved)
        stem = f"{result.equip_id}_{reading.capture_id}"
        (out / f"{stem}.md").write_text(to_markdown(result))
        (out / f"{stem}.json").write_text(json.dumps(to_record(result), indent=2))
        flagged = [f.name for f in result.fields if f.status.value != "MATCH"]
        rows.append((name, result.equip_id, result.overall.value, result.confidence,
                     ", ".join(flagged) or "-"))

    print(f"{'capture':<26}{'equip_id':<14}{'status':<14}{'min conf':<10}flagged fields")
    print("-" * 78)
    for name, eid, status, conf, flagged in rows:
        print(f"{name:<26}{eid or '?':<14}{status:<14}{conf:<10.2f}{flagged}")
    print(f"\nReports written to {out}/ (decision support only; inspector signs off).")


if __name__ == "__main__":
    main()
