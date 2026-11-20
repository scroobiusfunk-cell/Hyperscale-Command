# Capture gate — real-photo validation

Date: 2026-11-20. Ran `capture_gate` on 3 real degraded field photos (HPD-5A,
ASCO MTS, ABB In=800A), each as close / far / blurred / glare variants.
(Real photos NOT committed; this records the outcome.)

## Confirmed working
- **Blur rejection** is robust: sharp frames scored 300–3000 Laplacian variance,
  blurred scored 1–3. Clean separation.
- **Glare rejection** works: specular blowout scored 33–38% → fail.
- **White placards do NOT false-trip glare** (the concern raised during build):
  real white nameplates read 0.3–2.8% overexposed, far below the 5% threshold.
  The metric distinguishes white paint from specular glare correctly.

## Calibration finding — ACTION NEEDED before field use
- `min_sharpness = 300` was tuned on SYNTHETIC frames (good text ≈ 900–2000).
- On real DAT-compressed JPEG frames, genuinely-sharp placards scored only
  **310–650** — sitting right on the floor. JPEG compression removes the
  high-frequency detail the Laplacian measures.
- **Risk: false "blurry" rejections of good real frames.**
- **Fix:** recalibrate `min_sharpness` (and likely `min_text_height_px`) against
  real Ray-Ban Meta footage, not synthetic images. Expect to lower the sharpness
  floor to ~150–200. Do NOT overfit to the 3 spot-check photos.

## Notes
- `min_text_height_px = 16` for `placard_large` is reasonable: the ASCO placard
  at a modest framing scored ~10px and correctly failed — which is precisely the
  cue to guide the inspector closer. Validates the guidance premise.
- Metrics remain classical proxies for Android ML Kit on-device text recognition,
  which will replace them (and give a truer text-height signal) in the app.
