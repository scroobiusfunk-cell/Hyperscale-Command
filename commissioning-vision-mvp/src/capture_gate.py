"""Capture gate: scores live frames for OCR-readiness and decides when to auto-capture.

Pipeline position:  gate -> capture -> extract -> compare -> report

IMPORTANT -- these metrics are classical PROXIES.  In production the on-device
Android ML Kit text recognizer (running in the phone app on frames streamed from
the glasses) will report real text-block geometry and confidence; those should
replace sharpness / text_height_px / coverage here.  The proxies exist so the
gating logic, thresholds and audio/haptic feedback loop can be built and tested
offline with numpy + Pillow only (no OpenCV, no ML).

Feedback target: standard Ray-Ban Meta has NO in-lens display, so the gate emits
audio/haptic CUES (enum below); the app layer maps them to real sounds/vibration.

CONSERVATIVE PRINCIPLE: when uncertain, do NOT lock.  A withheld capture costs the
inspector a second; a saved unreadable frame costs a return trip.  Unreadable input,
tiny crops, no detected text, or any failing metric all resolve to "not LOCKED".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image

from .inspection_profile import InspectionProfile

# Frames larger than this (long edge) are downsized before scoring so pixel
# thresholds are resolution-independent. Never upscaled.
WORK_LONG_EDGE = 960

GLARE_LEVEL = 245        # gray level (0-255) counted as overexposed/near-white
GRAD_THRESH = 40.0       # gradient magnitude counted as a "strong" edge
ROW_DENSITY_THRESH = 0.04  # fraction of strong-edge pixels for a row to be text-like
MIN_BAND_PX = 4          # bands shorter than this are noise, not text lines
MAX_BAND_FRAC = 0.6      # bands taller than this fraction of the reticle aren't text lines
GAP_FILL_PX = 2          # close tiny gaps inside a band
MIN_CROP_PX = 32         # reticle crops smaller than this can't be trusted

ImageLike = Union[np.ndarray, str, Path, Image.Image]


class GateState(Enum):
    SEARCHING = "searching"
    CLOSE = "close"
    LOCKED = "locked"
    CAPTURED = "captured"


class Cue(Enum):
    """Audio/haptic feedback for a display-less wearable; the app renders these."""
    BEEP_SLOW = "beep_slow"      # SEARCHING: nothing usable yet
    BEEP_FAST = "beep_fast"      # CLOSE: text found, keep adjusting
    TONE_SOLID = "tone_solid"    # LOCKED: hold still (solid tone / sustained haptic)
    SHUTTER = "shutter"          # CAPTURED: frame saved
    NONE = "none"                # after capture, until reset()


_STATE_CUE = {GateState.SEARCHING: Cue.BEEP_SLOW, GateState.CLOSE: Cue.BEEP_FAST,
              GateState.LOCKED: Cue.TONE_SOLID, GateState.CAPTURED: Cue.SHUTTER}


@dataclass
class FrameScore:
    sharpness: float
    text_height_px: float
    coverage: float
    glare_frac: float
    sharpness_ok: bool = False
    text_height_ok: bool = False
    coverage_ok: bool = False
    glare_ok: bool = False
    passed: bool = False
    reasons: List[str] = field(default_factory=list)

    @property
    def n_pass(self) -> int:
        return sum([self.sharpness_ok, self.text_height_ok, self.coverage_ok, self.glare_ok])


# ---------------------------------------------------------------- image helpers

def _to_gray(image: ImageLike) -> np.ndarray:
    """Any supported input -> float32 grayscale (H, W), 0-255, downsized to working res."""
    if isinstance(image, (str, Path)):
        image = Image.open(image)
    if isinstance(image, Image.Image):
        image = np.asarray(image.convert("RGB"))
    arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[..., :3].astype(np.float32)
        arr = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    elif arr.ndim != 2:
        raise ValueError(f"unsupported image shape {arr.shape}")
    arr = arr.astype(np.float32)
    if arr.size and arr.max() <= 1.0 and arr.dtype.kind == "f":
        arr = arr * 255.0  # float images in 0-1
    h, w = arr.shape
    if max(h, w) > WORK_LONG_EDGE:
        s = WORK_LONG_EDGE / max(h, w)
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.BILINEAR)
        arr = np.asarray(im, dtype=np.float32)
    return arr


def _crop(gray: np.ndarray, reticle: Tuple[float, float, float, float]) -> np.ndarray:
    h, w = gray.shape
    x, y, rw, rh = reticle
    x0, y0 = int(round(x * w)), int(round(y * h))
    x1, y1 = int(round((x + rw) * w)), int(round((y + rh) * h))
    return gray[y0:y1, x0:x1]


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian (interior pixels), computed with numpy."""
    c = gray[1:-1, 1:-1]
    lap = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4.0 * c
    return float(lap.var())


def _runs(mask: np.ndarray) -> List[Tuple[int, int]]:
    """Contiguous True runs as (start, end_exclusive)."""
    padded = np.concatenate(([False], mask, [False]))
    d = np.diff(padded.astype(np.int8))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def text_bands(crop: np.ndarray) -> List[Tuple[int, int]]:
    """Find horizontal text-row bands from the row projection of edge density."""
    gy, gx = np.gradient(crop)
    edges = np.hypot(gx, gy) > GRAD_THRESH
    row_density = edges.mean(axis=1)
    rows = row_density >= ROW_DENSITY_THRESH
    # close small gaps (e.g. rows between a glyph's strokes) so one text line = one band
    runs = _runs(rows)
    merged: List[List[int]] = []
    for s, e in runs:
        if merged and s - merged[-1][1] <= GAP_FILL_PX:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    max_h = MAX_BAND_FRAC * crop.shape[0]
    return [(s, e) for s, e in merged if MIN_BAND_PX <= e - s <= max_h]


# --------------------------------------------------------------------- scoring

def score_frame(image: ImageLike, profile: InspectionProfile) -> FrameScore:
    """Score one frame against a profile. Never raises on bad pixels: fails closed."""
    try:
        gray = _to_gray(image)
        crop = _crop(gray, profile.reticle)
    except Exception as exc:  # unreadable file / bad array -> conservative fail
        return FrameScore(0.0, 0.0, 0.0, 1.0, reasons=[f"frame unreadable: {exc}"])
    if crop.shape[0] < MIN_CROP_PX or crop.shape[1] < MIN_CROP_PX or not np.isfinite(crop).all():
        return FrameScore(0.0, 0.0, 0.0, 1.0, reasons=["reticle crop too small or invalid"])

    sharp = laplacian_variance(crop)
    glare = float((crop >= GLARE_LEVEL).mean())
    bands = text_bands(crop)
    if bands:
        text_h = float(np.median([e - s for s, e in bands]))
        coverage = float(sum(e - s for s, e in bands) / crop.shape[0])
    else:
        text_h, coverage = 0.0, 0.0

    s = FrameScore(sharpness=sharp, text_height_px=text_h, coverage=coverage, glare_frac=glare)
    s.sharpness_ok = sharp >= profile.min_sharpness
    s.text_height_ok = text_h >= profile.min_text_height_px   # no bands -> 0 -> fails
    s.coverage_ok = coverage >= profile.min_coverage
    s.glare_ok = glare <= profile.max_glare_frac
    if not s.sharpness_ok:
        s.reasons.append(f"blurry: sharpness {sharp:.0f} < {profile.min_sharpness:.0f}")
    if not s.text_height_ok:
        s.reasons.append("no text found in reticle" if not bands else
                         f"too far: text {text_h:.0f}px < {profile.min_text_height_px:.0f}px")
    if not s.coverage_ok:
        s.reasons.append(f"text does not fill reticle: coverage {coverage:.2f} < {profile.min_coverage:.2f}")
    if not s.glare_ok:
        s.reasons.append(f"glare: {glare:.1%} overexposed > {profile.max_glare_frac:.0%}")
    s.passed = s.n_pass == 4
    return s


# ---------------------------------------------------------------- state machine

class GateStateMachine:
    """Feed frames one at a time; get (state, cue) back.

    SEARCHING -> CLOSE (text found, some metrics pass) -> LOCKED (all pass)
    -> CAPTURED after N consecutive LOCKED frames. Any failing frame resets the
    streak, so one lucky frame can never trigger a capture. Once captured, the
    machine holds CAPTURED (cue NONE) until reset().
    """

    def __init__(self, profile: InspectionProfile):
        self.profile = profile
        self.reset()

    def reset(self) -> None:
        self.state = GateState.SEARCHING
        self.streak = 0
        self.frame_index = -1
        self.last_score: Optional[FrameScore] = None
        self.captured_index: Optional[int] = None
        self.captured_frame: Optional[ImageLike] = None
        self._run: List[Tuple[int, ImageLike, float]] = []  # (index, frame, sharpness) of streak

    def update(self, frame: ImageLike) -> Tuple[GateState, Cue]:
        self.frame_index += 1
        if self.state == GateState.CAPTURED:
            return self.state, Cue.NONE
        score = score_frame(frame, self.profile)
        self.last_score = score
        if score.passed:
            self.streak += 1
            self._run.append((self.frame_index, frame, score.sharpness))
            if self.streak >= self.profile.consecutive_frames_required:
                # emit the sharpest frame of the locked run (not merely the last)
                idx, best, _ = max(self._run, key=lambda t: t[2])
                self.captured_index, self.captured_frame = idx, best
                self.state = GateState.CAPTURED
            else:
                self.state = GateState.LOCKED
        else:
            self.streak, self._run = 0, []
            close = score.text_height_px > 0 and score.n_pass >= 2
            self.state = GateState.CLOSE if close else GateState.SEARCHING
        return self.state, _STATE_CUE[self.state]


def select_best_frame(frames: Sequence[ImageLike], profile: InspectionProfile) -> Optional[int]:
    """Index of the sharpest PASSING frame in a burst; None if no frame passes."""
    best, best_sharp = None, -1.0
    for i, f in enumerate(frames):
        s = score_frame(f, profile)
        if s.passed and s.sharpness > best_sharp:
            best, best_sharp = i, s.sharpness
    return best
