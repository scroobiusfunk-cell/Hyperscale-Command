"""Voice layer for a display-less wearable: pure functions that map
(checklist item, gate state / result) -> VoiceLine(text to speak, cue to play).

The app speaks `text` through TTS and plays `cue`. Nothing here does I/O.
Gate cues reuse capture_gate.Cue; result cues are defined here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Union

from .capture_gate import Cue, GateState
from .checklist import ChecklistItem


class Phase(str, Enum):
    ANNOUNCE = "ANNOUNCE"   # tell the inspector what to inspect / where to look
    FRAMING = "FRAMING"     # coaching driven by gate state
    RESULT = "RESULT"       # outcome of the item


class ResultCue(Enum):
    CHIME_OK = "chime_ok"
    CHIME_ALERT = "chime_alert"
    CHIME_REVIEW = "chime_review"


AnyCue = Union[Cue, ResultCue]


@dataclass(frozen=True)
class VoiceLine:
    phase: Phase
    text: str
    cue: Optional[AnyCue] = None


_FRAMING_TEXT = {
    GateState.SEARCHING: "Move closer and center the label.",
    GateState.CLOSE: "Almost. Hold steady.",
    GateState.LOCKED: "Locked. Capturing.",
    GateState.CAPTURED: "Captured.",
}

# Spoken names for compared fields (acronyms read better as words).
_FIELD_SPEECH = {
    "manufacturer": "manufacturer", "model": "model number", "voltage": "voltage",
    "amp_rating": "amp rating", "aic_rating": "AIC rating", "poles": "pole count",
}


def announce_voice(item: ChecklistItem) -> VoiceLine:
    v = item.voice
    parts = [v.safety.rstrip(".") + "." if v.safety else "", f"Next: {item.prompt.rstrip('.')}.", f"{v.look.rstrip('.')}.",
             f"{v.frame.rstrip('.')}.", (v.hint.rstrip(".") + ".") if v.hint else ""]
    return VoiceLine(Phase.ANNOUNCE, " ".join(p.strip() for p in parts if p.strip()), None)


def framing_voice(item: ChecklistItem, state: GateState, cue: Cue) -> VoiceLine:
    """Coaching line for a gate state. Cue comes straight from the gate."""
    return VoiceLine(Phase.FRAMING, _FRAMING_TEXT[state], cue)


def result_voice(status: str, mismatched: Sequence[str] = (),
                 unclear: Sequence[str] = ()) -> VoiceLine:
    """status is an ItemStatus value: PASS / DISCREPANCY / NEEDS_REVIEW / NO_CAPTURE."""
    if status == "PASS":
        return VoiceLine(Phase.RESULT, "Match, confirmed.", ResultCue.CHIME_OK)
    if status == "DISCREPANCY":
        names = [_FIELD_SPEECH.get(f, f) for f in mismatched] or ["a rated value"]
        what = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        verb = "doesn't" if len(names) == 1 else "don't"
        return VoiceLine(Phase.RESULT,
                         f"Discrepancy: {what} {verb} match the submittal — flagged.",
                         ResultCue.CHIME_ALERT)
    if status == "NEEDS_REVIEW":
        return VoiceLine(Phase.RESULT, "Couldn't read it clearly — flagged for review.",
                         ResultCue.CHIME_REVIEW)
    if status == "NO_CAPTURE":
        return VoiceLine(Phase.RESULT,
                         "No clear capture. Nothing recorded. Adjust the angle or light and try again.",
                         ResultCue.CHIME_REVIEW)
    raise ValueError(f"unknown status {status!r}")
