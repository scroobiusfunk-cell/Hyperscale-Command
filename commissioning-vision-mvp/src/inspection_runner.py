"""Checklist-driven inspection runner.

    checklist item -> voice -> capture gate -> capture -> extract -> compare -> report

The item is the spine: it carries the voice script, the gate profile key, the
registry reference (plus optional expected-value overrides) and the evidence rule.
Frames are injected by the caller (a live camera stream in production, simulated
sequences in the demo/tests), so the runner itself does no I/O.
"""
from __future__ import annotations

import dataclasses
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Union

from .capture_gate import Cue, GateState, GateStateMachine
from .checklist import Checklist, ChecklistItem
from .compare import (FieldStatus, OverallStatus, VerificationResult, compare)
from .extract import Extractor, MockExtractor, NameplateReading
from .inspection_profile import get_profile
from .registry import ApprovedItem, Registry
from .report import to_markdown as item_markdown, to_record as item_record
from .voice import (Phase, VoiceLine, announce_voice, framing_voice, result_voice)

# An extractor is either a real Extractor (called with the captured frame/path) or a
# callable (frame, item) -> NameplateReading, which lets tests/demos inject readings.
ExtractorLike = Union[Extractor, Callable[[Any, ChecklistItem], NameplateReading]]


class ItemStatus(str, Enum):
    PASS = "PASS"
    DISCREPANCY = "DISCREPANCY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NO_CAPTURE = "NO_CAPTURE"      # gate never locked: nothing recorded, never a pass


@dataclass
class ItemResult:
    item: ChecklistItem
    status: ItemStatus
    reading: Optional[NameplateReading] = None
    comparison: Optional[VerificationResult] = None
    evidence_ref: str = ""
    voice: list[VoiceLine] = field(default_factory=list)
    gate_trace: list[tuple[int, GateState, Cue]] = field(default_factory=list)  # state changes
    notes: list[str] = field(default_factory=list)

    @property
    def transcript(self) -> list[tuple[Phase, str, Any]]:
        return [(v.phase, v.text, v.cue) for v in self.voice]


class SidecarExtractor:
    """Demo/test helper: wraps MockExtractor, mapping item id -> sidecar JSON path.
    The frame is ignored (a real extractor would OCR it)."""

    def __init__(self, sidecars: Mapping[str, Path | str]):
        self._sidecars, self._mock = dict(sidecars), MockExtractor()

    def __call__(self, frame: Any, item: ChecklistItem) -> NameplateReading:
        return self._mock.extract(self._sidecars[item.id])


def _expected(item: ChecklistItem, registry: Registry) -> Optional[ApprovedItem]:
    """Registry record for the item, with expected_fields overriding per field."""
    approved = registry.get(item.equip_id)
    if approved is not None and item.expected_fields:
        approved = dataclasses.replace(approved, **item.expected_fields)
    return approved


def _read(extractor: ExtractorLike, frame: Any, item: ChecklistItem) -> NameplateReading:
    if isinstance(extractor, Extractor):
        return extractor.extract(frame)   # real extractors take a path to the saved frame
    return extractor(frame, item)


def run_item(item: ChecklistItem, frames: Iterable[Any], registry: Registry,
             extractor: ExtractorLike) -> ItemResult:
    res = ItemResult(item=item, status=ItemStatus.NO_CAPTURE)

    def say(line: VoiceLine) -> None:
        res.voice.append(line)

    say(announce_voice(item))

    gate = GateStateMachine(get_profile(item.profile_key))
    last_state: Optional[GateState] = None
    for i, frame in enumerate(frames):
        state, cue = gate.update(frame)
        if state != last_state:                       # speak only on state change
            res.gate_trace.append((i, state, cue))
            say(framing_voice(item, state, cue))
            last_state = state
        if state == GateState.CAPTURED:
            break

    if gate.captured_frame is None:                   # gate never locked: no fabricated pass
        res.notes.append("Gate never locked; no capture.")
        say(result_voice(ItemStatus.NO_CAPTURE.value))
        return res

    approved = _expected(item, registry)
    try:
        reading = _read(extractor, gate.captured_frame, item)
    except Exception as exc:                          # extractor failure -> human review
        res.status = ItemStatus.NEEDS_REVIEW
        res.notes.append(f"Extraction failed: {exc}")
        say(result_voice(res.status.value))
        return res
    res.reading = reading
    res.evidence_ref = reading.evidence_photo or f"frame:{item.id}#{gate.captured_index}"

    if approved is None:
        res.status = ItemStatus.NEEDS_REVIEW
        res.notes.append(f"equip_id {item.equip_id!r} not in registry.")
        say(result_voice(res.status.value))
        return res

    res.comparison = compare(reading, approved)
    res.status = ItemStatus(res.comparison.overall.value)
    if res.status == ItemStatus.PASS and item.evidence_required and not reading.evidence_photo:
        res.status = ItemStatus.NEEDS_REVIEW          # a pass without evidence is not a pass
        res.notes.append("Evidence required but no photo reference on the reading.")

    bad = [f.name for f in res.comparison.fields if f.status == FieldStatus.MISMATCH]
    say(result_voice(res.status.value, mismatched=bad))
    return res


# ------------------------------------------------------------------- report

@dataclass
class InspectionReport:
    checklist_id: str
    checklist_name: str
    results: list[ItemResult]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def summary(self) -> dict[str, int]:
        c = Counter(r.status for r in self.results)
        out = {s.value: c.get(s, 0) for s in ItemStatus}
        out["TOTAL"] = len(self.results)
        return out

    def to_record(self) -> dict:
        """Structured record; per-item records reuse report.to_record."""
        items = []
        for r in self.results:
            row: dict[str, Any] = {
                "item_id": r.item.id, "prompt": r.item.prompt, "equip_id": r.item.equip_id,
                "status": r.status.value, "evidence_ref": r.evidence_ref, "notes": r.notes,
                "voice_transcript": [{"phase": p.value, "text": t, "cue": getattr(c, "value", None)}
                                     for p, t, c in r.transcript],
            }
            if r.comparison:
                row["verification"] = item_record(r.comparison, self.generated_at)
            items.append(row)
        return {"checklist_id": self.checklist_id, "checklist_name": self.checklist_name,
                "generated_at": self.generated_at, "summary": self.summary, "items": items,
                "inspector": {"name": "", "signature": "", "signed_at": "", "notes": ""}}

    def to_json(self) -> str:
        return json.dumps(self.to_record(), indent=2)

    def to_markdown(self) -> str:
        s = self.summary
        L = [f"# Inspection Report: {self.checklist_name}", "",
             f"Checklist: {self.checklist_id} | Generated: {self.generated_at}", "",
             "> Decision support only. Results are not an acceptance; the inspector must review and sign.",
             "", "## Summary", "",
             f"- Items: {s['TOTAL']}",
             f"- Pass: {s['PASS']}", f"- Discrepancy: {s['DISCREPANCY']}",
             f"- Needs review: {s['NEEDS_REVIEW']}", f"- No capture: {s['NO_CAPTURE']}", "",
             "| Item | Equipment | Status | Evidence |", "|---|---|---|---|"]
        for r in self.results:
            L.append(f"| {r.item.id} | {r.item.equip_id} | {r.status.value} | `{r.evidence_ref or 'none'}` |")
        L.append("")
        for r in self.results:
            L += [f"## {r.item.id}: {r.item.prompt}", "", f"**Status: {r.status.value}**", ""]
            L += [f"- Note: {n}" for n in r.notes]
            if r.comparison:
                # reuse the single-item report; demote headings by two levels, drop its own sign-off block
                body = item_markdown(r.comparison, self.generated_at).split("## Inspector sign-off")[0]
                body = "\n".join(("##" + ln) if ln.startswith("#") else ln for ln in body.splitlines())
                L += ["", body.strip(), ""]
            elif not r.notes:
                L.append("")
        L += ["## Inspector sign-off", "",
              "- Inspector name: ______________________",
              "- Signature / date: ______________________",
              "- Notes: ", ""]
        return "\n".join(L)


def run_checklist(checklist: Checklist, frame_sources: Mapping[str, Iterable[Any]],
                  registry: Registry, extractor: ExtractorLike) -> InspectionReport:
    """frame_sources maps item id -> frames for that item. A missing source means no
    frames arrived, which yields NO_CAPTURE for that item."""
    results = [run_item(it, frame_sources.get(it.id, []), registry, extractor)
               for it in checklist.items]
    return InspectionReport(checklist.id, checklist.name, results)
