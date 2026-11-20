# Commissioning Vision MVP

Offline prototype that checks a photo-derived electrical nameplate reading against the **approved submittal** record and produces an evidence-backed verification report.

## Philosophy: human signs off, verification is conservative

This tool is decision **support**, not the authority. An inspector signs every report (the sign-off block is left blank by design). Therefore:

- `PASS` only if every compared field is read with confidence >= 0.75 **and** matches after normalization.
- Any confident disagreement -> `DISCREPANCY` (safety-critical fields such as voltage, amps, AIC are highlighted).
- Anything missing, garbled, low-confidence, partial (e.g. "480" vs approved "480Y/277V"), or tagged to a different item -> `NEEDS_REVIEW`.
- When in doubt, `NEEDS_REVIEW`. The tool never guesses.

## Architecture

```
src/registry.py  approved records (dataclasses), lookup by equip_id / type
src/extract.py   NameplateReading + abstract Extractor
                   MockExtractor   reads sidecar JSON (demo/tests, offline)
                   VisionExtractor stub - where a real vision/OCR call goes
src/compare.py   normalize + per-field MATCH/MISMATCH/MISSING/UNVERIFIABLE -> overall status
src/report.py    JSON record + Markdown inspection report
demo.py          end-to-end run over data/captures/*.json -> out/
```

## Capture gate

`src/capture_gate.py` + `src/inspection_profile.py` sit in front of extraction so the inspector never saves an unreadable frame:

```
glasses frames -> capture gate -> capture -> extract.py -> compare -> report
```

Each live frame is scored inside a profile's reticle (`placard_large`, `nameplate_small`, `serial_tag`) for sharpness (Laplacian variance), text height in px, reticle coverage and glare. `GateStateMachine.update(frame)` returns `(state, cue)`; it auto-captures only after N *consecutive* all-pass frames (any failure resets the count) and keeps the sharpest frame of that run. `select_best_frame` picks the best still from a burst. Conservative by design: unreadable, blank or ambiguous frames never lock.

**Feedback is audio/haptic, not visual** - standard Ray-Ban Meta has no in-lens display. The gate emits a `Cue` per state and the phone app turns it into sound/vibration:

| State | Cue | Meaning |
|---|---|---|
| SEARCHING | `BEEP_SLOW` | nothing usable yet |
| CLOSE | `BEEP_FAST` | text found, adjust distance/angle/light |
| LOCKED | `TONE_SOLID` | hold still |
| CAPTURED | `SHUTTER` | frame saved |

The metrics are **classical numpy proxies** (no OpenCV, no ML) for what Android ML Kit on-device text recognition will report in production; thresholds are in pixels at a 960px working resolution and need field calibration. Try it: `python spike/gate_demo.py` (synthetic frames only).

## Inspection runner (checklist-driven)

A QA/QC **checklist** is the spine. Each `ChecklistItem` (`src/checklist.py`) binds everything one inspection step needs: the inspection question, the `equip_id` into the registry, the gate `profile_key` (`placard_large` / `nameplate_small` / `serial_tag`), a `VoiceScript` (where to look, how to frame, optional hint/safety line), optional `expected_fields` overriding registry values, and an `evidence_required` flag. The inspector wears display-less glasses, so everything is voice + audio cues.

```
checklist -> voice -> gate -> capture -> extract -> compare -> report
```

1. `src/voice.py` (pure functions) speaks the ANNOUNCE line, coaches framing from gate state (SEARCHING "Move closer...", CLOSE "Almost, hold steady", LOCKED, CAPTURED) and speaks the RESULT. Each line is `(phase, text, cue)`: the app does TTS on text and plays the cue (gate `Cue` or a result chime).
2. `src/inspection_runner.py::run_item` drives `GateStateMachine` over injected frames, extracts a `NameplateReading` from the captured frame, runs `compare` against the registry record (with overrides applied) and returns an `ItemResult` (PASS / DISCREPANCY / NEEDS_REVIEW / NO_CAPTURE, reading, comparison, evidence ref, voice transcript, gate trace).
3. If the gate never locks the item is `NO_CAPTURE` with a retry prompt; nothing is fabricated. A PASS with `evidence_required` but no photo reference is downgraded to NEEDS_REVIEW.
4. `run_checklist` aggregates into an `InspectionReport` (summary counts, per-item sections reusing `report.py`, JSON + Markdown, blank inspector sign-off).

The extractor can be a real `Extractor` or a callable `(frame, item) -> NameplateReading`, so demos/tests inject readings. Try it: `python spike/inspection_demo.py` (simulated frames and readings; sample checklist in `data/checklists/sample_electrical.json`).

## Plugging in glasses/DAT camera and a real vision API

Both are swappable adapters at the `Extractor` seam in `src/extract.py`; `compare` and `report` do not change.

- **Real vision/OCR API:** implement `VisionExtractor.extract()` (the TODO documents the exact contract: per-field value + calibrated confidence, null when illegible, never guess).
- **Glasses / DAT camera:** the capture client feeds the photo (and any tag/QR id) to an Extractor, which returns a `NameplateReading` with `evidence_photo` set to the stored image.

## Run

```
python demo.py          # prints summary table, writes out/*.md and out/*.json
python -m pytest -q     # needs pytest
```

Core demo is standard library only; the capture gate needs `numpy` and `Pillow`. No network, no API keys.

## Limitations & not yet built

- **No real OCR/vision yet.** Captures are hand-made sidecar JSON; extraction accuracy is unproven.
- **Nameplate legibility** (glare, corrosion, angle, small print, multi-language plates) will drive many NEEDS_REVIEW results; confidence calibration of a real model is untested.
- **Offline data halls:** field connectivity is poor; the real tool needs on-device/queued operation and sync.
- **Integrations:** no Procore / Autodesk Construction Cloud link for pulling submittals or pushing results; the registry is a local JSON file.
- Compared fields are limited to manufacturer, model, voltage, amps, AIC, poles. Model numbers require exact (punctuation-insensitive) match; there is no catalog-aware equivalence, and the manufacturer alias list is small.
- No authentication, audit-log immutability, or signature capture; sign-off is a blank form.
