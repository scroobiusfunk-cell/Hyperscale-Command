"""Capture-gate tests on SYNTHETIC images only (Pillow-drawn placards, no real photos)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.capture_gate import (Cue, GateState, GateStateMachine, score_frame,
                              select_best_frame)
from src.inspection_profile import PROFILES, get_profile

PROFILE = PROFILES["nameplate_small"]
W, H = 640, 480
LINES = ["HPD-5A", "35KV 600A", "SER 884213"]


def make_frame(font_size=40) -> Image.Image:
    """Light placard (gray 215, below the glare level) with dark text, centered."""
    im = Image.new("L", (W, H), 120)
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, W - 40, H - 40], fill=215)
    font = ImageFont.load_default(font_size)
    step = int(font_size * 1.4)
    y = H // 2 - int(step * 1.5)
    for line in LINES:
        w = d.textlength(line, font=font)
        d.text(((W - w) / 2, y), line, font=font, fill=20)
        y += step
    return im


def good(): return make_frame(40)
def far(): return make_frame(14)
def blurred(radius=3): return make_frame(40).filter(ImageFilter.GaussianBlur(radius))


def glare() -> Image.Image:
    im = make_frame(40)
    ImageDraw.Draw(im).rectangle([250, 130, 450, 280], fill=255)  # blown-out patch
    return im


def test_profiles_sane():
    assert set(PROFILES) >= {"placard_large", "nameplate_small", "serial_tag"}
    h = [PROFILES[n].min_text_height_px for n in ("placard_large", "nameplate_small", "serial_tag")]
    assert h == sorted(h) and len(set(h)) == 3
    assert get_profile("serial_tag").reticle[2] < PROFILES["placard_large"].reticle[2]


def test_good_passes():
    s = score_frame(good(), PROFILE)
    assert s.passed and not s.reasons
    assert s.sharpness_ok and s.text_height_ok and s.coverage_ok and s.glare_ok


def test_far_fails_text_height():
    s = score_frame(far(), PROFILE)
    assert not s.passed and not s.text_height_ok
    assert any("too far" in r for r in s.reasons)


def test_blurred_fails_sharpness():
    s = score_frame(blurred(), PROFILE)
    assert not s.passed and not s.sharpness_ok
    assert any("blurry" in r for r in s.reasons)


def test_glare_fails_glare():
    s = score_frame(glare(), PROFILE)
    assert not s.passed and not s.glare_ok
    assert any("glare" in r for r in s.reasons)


def test_accepts_array_and_path(tmp_path):
    p = tmp_path / "f.png"
    good().save(p)
    assert score_frame(p, PROFILE).passed
    assert score_frame(np.asarray(good().convert("RGB")), PROFILE).passed


def test_conservative_on_garbage():
    assert not score_frame(np.full((H, W), 128, np.uint8), PROFILE).passed   # blank wall
    assert not score_frame(np.zeros((4, 4)), PROFILE).passed                 # tiny
    assert not score_frame("/nonexistent/frame.png", PROFILE).passed         # unreadable


def test_state_machine_captures_after_n_good():
    sm = GateStateMachine(PROFILE)
    n = PROFILE.consecutive_frames_required
    out = [sm.update(good()) for _ in range(n)]
    assert [s for s, _ in out[:-1]] == [GateState.LOCKED] * (n - 1)
    assert out[-1] == (GateState.CAPTURED, Cue.SHUTTER)
    assert sm.captured_index is not None and sm.captured_frame is not None
    assert sm.update(good()) == (GateState.CAPTURED, Cue.NONE)  # captures once


def test_cues_per_state():
    sm = GateStateMachine(PROFILE)
    assert sm.update(np.full((H, W), 128, np.uint8)) == (GateState.SEARCHING, Cue.BEEP_SLOW)
    assert sm.update(far()) == (GateState.CLOSE, Cue.BEEP_FAST)
    assert sm.update(good()) == (GateState.LOCKED, Cue.TONE_SOLID)


def test_single_good_frame_amid_failures_does_not_capture():
    sm = GateStateMachine(PROFILE)
    n = PROFILE.consecutive_frames_required
    # (n-1) good, a failure, (n-1) good: never n in a row
    seq = [good()] * (n - 1) + [blurred()] + [good()] * (n - 1) + [far()] + [good()]
    for f in seq:
        state, _ = sm.update(f)
        assert state != GateState.CAPTURED
    assert sm.captured_index is None


def test_select_best_frame_picks_sharpest_passing():
    frames = [far(), blurred(), blurred(0.8), good(), blurred(0.3)]
    scores = [score_frame(f, PROFILE) for f in frames]
    passing = [i for i, s in enumerate(scores) if s.passed]
    assert passing, "need at least one passing frame for this test"
    expect = max(passing, key=lambda i: scores[i].sharpness)
    assert select_best_frame(frames, PROFILE) == expect
    assert select_best_frame([far(), blurred()], PROFILE) is None  # nothing passes -> no pick
