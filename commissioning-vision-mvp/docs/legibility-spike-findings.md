# Legibility spike — can DAT-quality camera read field nameplates?

Date: 2026-11-20. Run on 13 real QA/QC field photos (G&W 35kV switches, ABB
Ekip trip units / SACE Tmax, ASCO transfer switches, terminal blocks).

## Method
- Degraded each original to Meta DAT's **best-case** camera: fit within
  720×1280 (DAT "high" stream preset) + JPEG quality 42 to mimic Bluetooth
  per-frame compression. Script: `scratchpad/spike/degrade.py`.
- Originals 1600×1200 (already WhatsApp-compressed) or 4000×3000 → ~960×720,
  40–67 KB JPEGs (≈98% data loss on the big ones).
- Read the degraded frames with a capable vision model; compared to ground
  truth from the originals.

## Results — what survives DAT 720p

| Field class | Example | Survives? |
|---|---|---|
| Large equipment-ID placard | HPD-5A · 35KV 600A · FED FROM: MSG-C · MTS-1HMDP08 · 480V 3PH 3W | ✅ clean pass |
| Manufacturer + trip-unit model | ABB · ASCO · In=800A/3200A · SACE Tmax · Ekip Hi-Touch LSIG | ✅ pass |
| Phase / major wire labels | A B C · B1C101 | ✅ pass |
| Arc-flash sticker values | incident energy, boundary, approach | ⚠️ marginal (close framing only) |
| Trip-unit terminal labels | S51, Trip Unit I/O, 25 D1 C11… | ⚠️ marginal (tight only) |
| Seal-tag handwriting | 4/23 · R.A.H | ⚠️ marginal |
| Stamped serial numbers | DEDA71K S/N 73390X001 | ❌ fail |
| Terminal-block point numbers | 3–35 grid, 31BG-D/N/E | ❌ fail |
| Dense fine print / instructions | ATS menu, warning legalese | ❌ fail (not QA-relevant) |

Key secondary finding: **framing distance dominates.** The same ABB trip-unit
terminal labels were readable in a tight close-up and illegible in a wider shot.

## Honest caveat
The simulation is a clean downscale + JPEG. Real glasses add motion blur
(hands-free), glare on glossy placards and plastic-sleeved arc-flash stickers,
oblique angles, auto-exposure swings, and dropped BT frames. Real-world
legibility will be **≤** this. Big placards have margin; the "marginal" rows
will mostly degrade to fail. A hardware spike on real glasses is still required
to confirm — especially whether `capturePhoto()` stills beat the stream.

## Product implication
- **Glasses = hands-free equipment-tag & rating verification + triage.**
  Look at gear → confirm tag / voltage / amperage / fed-from against the
  submittal → auto-log evidence. This is the high-frequency, high-value check,
  and it passes at DAT quality.
- **Fine detail (serials, terminal mapping, torque stamps) = guided close-up
  still or flagged for a phone photo.** The app should classify each target and
  coach framing for small-text items.

## Next
1. Wire a real OCR/vision model into `extract.py::VisionExtractor` and re-run
   this exact set to get quantitative field-level accuracy (not just a human read).
2. Build the Android DAT mock-device app; feed captured frames to the engine.
3. Hardware spike: real glasses, confirm still-capture resolution + glare/motion.
