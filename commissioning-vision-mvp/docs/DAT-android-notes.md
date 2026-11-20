# Meta DAT (Wearables Device Access Toolkit) — Android integration notes

Verified 2026-11-20 against Meta's official Wearables Developer Center.
Marked **[OFFICIAL]** vs **[UNCONFIRMED]**. Re-check exact numbers on the live
pages before locking design — some come from fetched-page summaries.

## Status
- **[OFFICIAL]** Official name: *Meta Wearables Device Access Toolkit (DAT)*.
  Docs: https://wearables.developer.meta.com/docs/develop/dat
- **[OFFICIAL]** "DAT 1.0" = stable, supported release; rollout from 2026-09-30.
  Docs currently v1.1; Android SDK example shows `1.1.0`.
- **[OFFICIAL]** Android SDK is first-party: https://github.com/facebook/meta-wearables-dat-android
- **[OFFICIAL, caveat]** README still says "developer preview" and **public app
  publishing is not open yet** ("soon"). Does NOT block building/sideloading an
  internal tool. Whether "preview" is stale or applies only to publishing: unclear.

## Android developer surface  **[OFFICIAL]**
- Native **Kotlin** SDK on **Maven Central**, group `com.meta.wearable`.
  Artifacts: `mwdat-core`, `mwdat-camera`, `mwdat-display`, `mwdat-inputs`,
  `mwdat-motion`, `mwdat-mockdevice`, `mwdat-speech`.
- Manifest perms: `BLUETOOTH`, `BLUETOOTH_CONNECT`, `INTERNET` (+ `CAMERA` only
  if using phone camera as the mock feed). URI-scheme intent filter for Meta AI
  app callback. `APPLICATION_ID` + `CLIENT_TOKEN` metadata (both `0` in Dev Mode,
  attestation skipped).
- Flow: `Wearables.initialize()` -> `startRegistration()` (hands off to Meta AI
  app) -> observe `registrationState` / `devices` -> request camera via
  `RequestPermissionContract` -> `createSession()` -> `session.start()` -> add
  camera when STARTED. One session per device; a stopped session can't restart;
  pauses on hinge close / removal / tap.
- **Architecture: app runs on the PHONE; glasses are a Bluetooth peripheral**
  reached *through the Meta AI app*. Integration guide:
  https://wearables.developer.meta.com/docs/develop/dat/build-integration-android/

## Camera — the critical constraint for OUR use case
- **[OFFICIAL]** Stream presets: **720x1280** (high), 504x896, 360x640.
  FPS: 2/7/15/24/30. Bluetooth-Classic-limited; auto-drops quality under load;
  per-frame compression means delivered image can look worse than nominal res.
- **[OFFICIAL]** Still capture: `capturePhoto()` during an active stream returns
  JPEG. There is a separate "high-quality photo capture" guide (not yet fetched).
- **[UNCONFIRMED]** Max still resolution / any quality param on `capturePhoto`.
  An old forum post mentioned 1440x1080 early samples — unverified.
- **RISK:** nameplate legibility. Reading model / AIC / voltage off a breaker at
  720p + BT compression is the single biggest open question. **Do not assume
  high-res stills until tested on hardware.**

## Mock Device Kit  **[OFFICIAL]**
- Ships as `mwdat-mockdevice` (Maven). Simulates pairing, device state,
  permissions, and media streaming. **Phone camera can be the mock feed.**
- Does NOT support display glasses. Audio/motion simulation scope: unconfirmed.
- => We can build + run the Android app end-to-end WITHOUT glasses.

## Access / approval  **[OFFICIAL]**
- Need a Meta Managed Account + Wearables Developer Center account; set up org +
  project; register the integration to request permissions. Dev Mode skips
  attestation. Share builds with testers via release channels.
- Nothing blocks starting development of an internal field tool.

## Other constraints
- **[OFFICIAL]** Mic = Bluetooth HFP, 8 kHz mono (irrelevant to us). Only DAT can
  use the glasses camera/mic.
- **[UNCONFIRMED]** Offline behavior (shielded data hall!), latency, battery
  during streaming, background/continuous-capture limits, `mwdat-motion` contents,
  minimum Android API level.

## Implication for the build
1. **De-risk legibility FIRST, before writing Kotlin** — simulate DAT quality
   (downscale to 720x1280 + JPEG compress) on real nameplate photos and run them
   through extraction. Cheap, and it decides whether the glasses path is viable.
2. Then scaffold the Android mock-device app (phone camera as feed) -> captures a
   frame/still -> hands it to the verification engine via a defined API.
3. Hardware spike on real glasses early to confirm still resolution + offline.
