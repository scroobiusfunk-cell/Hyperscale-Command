"""Capture-gate demo on a SYNTHETIC sequence (no real photos).

Run from the project dir:  python spike/gate_demo.py
Simulates an inspector walking up to a nameplate: blurry/far frames, then good ones.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.capture_gate import GateStateMachine
from src.inspection_profile import get_profile

W, H = 640, 480


def frame(font_size, blur=0.0, glare=False):
    im = Image.new("L", (W, H), 120)
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, W - 40, H - 40], fill=215)
    font, step = ImageFont.load_default(font_size), int(font_size * 1.4)
    y = H // 2 - int(step * 1.5)
    for line in ["HPD-5A", "35KV 600A", "SER 884213"]:
        d.text(((W - d.textlength(line, font=font)) / 2, y), line, font=font, fill=20)
        y += step
    if glare:
        d.rectangle([250, 130, 450, 280], fill=255)
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


SEQUENCE = [
    ("walking up, far", frame(12)),
    ("far", frame(16)),
    ("closer, blurred", frame(40, blur=3)),
    ("closer, blurred", frame(40, blur=2)),
    ("glare from light", frame(40, glare=True)),
    ("good", frame(40)),
    ("good", frame(40, blur=0.3)),
    ("good", frame(42)),
    ("good", frame(40)),
    ("good (not reached)", frame(40)),
]


def main():
    profile = get_profile("nameplate_small")
    sm = GateStateMachine(profile)
    print(f"profile: {profile.label}  (need {profile.consecutive_frames_required} consecutive good frames)\n")
    print(f"{'#':>2} {'sharp':>7} {'text_px':>7} {'glare':>6}  {'state':<10} {'cue':<11} note")
    for i, (note, img) in enumerate(SEQUENCE):
        state, cue = sm.update(img)
        s = sm.last_score
        print(f"{i:>2} {s.sharpness:7.0f} {s.text_height_px:7.1f} {s.glare_frac:6.1%}  "
              f"{state.name:<10} {cue.name:<11} {note}")
        if sm.captured_index is not None:
            break
    print(f"\ncaptured frame index: {sm.captured_index}")


if __name__ == "__main__":
    main()
