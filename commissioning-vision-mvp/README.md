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

## Plugging in glasses/DAT camera and a real vision API

Both are swappable adapters at the `Extractor` seam in `src/extract.py`; `compare` and `report` do not change.

- **Real vision/OCR API:** implement `VisionExtractor.extract()` (the TODO documents the exact contract: per-field value + calibrated confidence, null when illegible, never guess).
- **Glasses / DAT camera:** the capture client feeds the photo (and any tag/QR id) to an Extractor, which returns a `NameplateReading` with `evidence_photo` set to the stored image.

## Run

```
python demo.py          # prints summary table, writes out/*.md and out/*.json
python -m pytest -q     # needs pytest
```

Standard library only; no network, no API keys.

## Limitations & not yet built

- **No real OCR/vision yet.** Captures are hand-made sidecar JSON; extraction accuracy is unproven.
- **Nameplate legibility** (glare, corrosion, angle, small print, multi-language plates) will drive many NEEDS_REVIEW results; confidence calibration of a real model is untested.
- **Offline data halls:** field connectivity is poor; the real tool needs on-device/queued operation and sync.
- **Integrations:** no Procore / Autodesk Construction Cloud link for pulling submittals or pushing results; the registry is a local JSON file.
- Compared fields are limited to manufacturer, model, voltage, amps, AIC, poles. Model numbers require exact (punctuation-insensitive) match; there is no catalog-aware equivalence, and the manufacturer alias list is small.
- No authentication, audit-log immutability, or signature capture; sign-off is a blank form.
