"""Inspection profiles: how to frame each class of equipment text for the capture gate.

A profile tells the gate (a) where in the frame the target text should sit (the
reticle -- the inspector aims the glasses so the text falls inside it) and
(b) how legible the text must be before a frame is worth saving.

All pixel thresholds are expressed at the gate's WORKING RESOLUTION (long edge
<= capture_gate.WORK_LONG_EDGE px); score_frame downsizes larger frames so
thresholds mean the same thing regardless of camera resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class InspectionProfile:
    name: str
    label: str                                   # human-readable, e.g. spoken by the app
    reticle: Tuple[float, float, float, float]   # (x, y, w, h), each 0-1 of the frame
    min_text_height_px: float                    # KEY legibility threshold (text-band height)
    min_sharpness: float                         # Laplacian variance floor (reticle crop)
    max_glare_frac: float                        # max fraction of near-white pixels
    consecutive_frames_required: int             # N consecutive good frames before capture
    min_coverage: float = 0.15                   # min fraction of reticle rows that are text

    def __post_init__(self):
        x, y, w, h = self.reticle
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1
                and x + w <= 1.0001 and y + h <= 1.0001):
            raise ValueError(f"reticle out of range: {self.reticle}")
        if self.consecutive_frames_required < 1:
            raise ValueError("consecutive_frames_required must be >= 1")


# Reasoning: the smaller and denser the target text, the tighter the reticle (forces
# the wearer to move in, which is what actually makes small print legible) and the
# larger the text must appear in pixels. Smaller/denser targets also demand more
# stable frames, since small-print OCR is the first thing to break on motion.
PROFILES: Dict[str, InspectionProfile] = {
    # Big equipment-ID sign, read from a few metres. Loose reticle (wearer need not
    # aim precisely); characters only need to be modestly tall in the frame.
    "placard_large": InspectionProfile(
        name="placard_large", label="Equipment ID placard",
        reticle=(0.10, 0.20, 0.80, 0.60),
        min_text_height_px=16, min_sharpness=300.0, max_glare_frac=0.05,
        consecutive_frames_required=3, min_coverage=0.12),
    # Breaker/panel/transformer nameplate: dense multi-line small print. Tighter
    # reticle, taller text required (rated V/A/kA digits must be unambiguous).
    "nameplate_small": InspectionProfile(
        name="nameplate_small", label="Equipment nameplate",
        reticle=(0.20, 0.25, 0.60, 0.50),
        min_text_height_px=22, min_sharpness=400.0, max_glare_frac=0.04,
        consecutive_frames_required=4, min_coverage=0.15),
    # Serial / asset tag: tiny, one or two lines, a single wrong digit matters.
    # Very tight reticle, highest height requirement, strictest glare and stability.
    "serial_tag": InspectionProfile(
        name="serial_tag", label="Serial / asset tag",
        reticle=(0.30, 0.35, 0.40, 0.30),
        min_text_height_px=30, min_sharpness=500.0, max_glare_frac=0.03,
        consecutive_frames_required=5, min_coverage=0.20),
}


def get_profile(name: str) -> InspectionProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(f"unknown profile {name!r}; choose from {sorted(PROFILES)}") from None
