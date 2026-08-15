# Hyperscale Command

A multi-protocol smart-home discovery and control console for Android, built for the
**Samsung Galaxy Z Fold 8** and bridged to **Homey Pro** for everything a phone's radios
cannot reach.

Your house has devices from a dozen brands speaking a dozen protocols. This app finds all of
them, works out what they are, merges them into one inventory, and — through Homey Pro —
controls them from one place.

---

## What it does

**Finds things.** Five scanner engines run concurrently over every protocol an Android handset
can physically speak:

| Engine | Protocols covered |
| --- | --- |
| mDNS / DNS-SD | Matter, HomeKit, Google Cast, AirPlay, Hue, Sonos, ESPHome, Shelly, Nanoleaf, Thread border routers, Homey, Home Assistant, MQTT, and ~30 generic service types |
| SSDP / UPnP | UPnP, DLNA, Sonos, WeMo, Roku, LG webOS, Samsung Tizen, Yeelight (port 1982), Govee (port 4001), ONVIF |
| UDP probe | LIFX, TP-Link Kasa, WiZ, Tuya, Xiaomi miIO, KNXnet/IP, BACnet/IP, CoAP, MQTT-SN, ONVIF WS-Discovery |
| Bluetooth LE | BLE, Bluetooth Mesh, Matter commissioning beacons, SwitchBot, HomeKit-over-BLE, Govee |
| Network sweep | Subnet sweep plus a signature-port matrix — MQTT, Modbus TCP, ESPHome, Sonos, Roku, KNX, Nanoleaf, Kasa, Crestron, C-Bus, and more |

**Identifies them.** Evidence from every protocol is fused: mDNS TXT records, SSDP device
description XML, BLE manufacturer data and Matter commissioning payloads, MAC OUI vendor lookup,
HomeKit accessory categories, and Homey's own driver metadata. A device seen four different ways
becomes **one row**, not four.

**Syncs and controls them.** Homey Pro's local Web API brings in every device on a radio the
phone doesn't have, with working controls.

## The honest part: what a phone can and cannot see

An Android handset has Wi-Fi, Bluetooth and NFC. That is all. **Zigbee, Z-Wave, Thread end
devices, 433/868/315 MHz RF, infrared, EnOcean, and powerline protocols like X10 and Insteon are
physically unreachable from a phone**, no matter what software is installed.

Rather than quietly omit them or offer a scan that could never succeed, the app catalogues all
of them and labels each one **Direct scan**, **Via hub**, or **Direct + hub**. The ones marked
*Via hub* arrive through Homey Pro, which does have those radios. The Protocols screen explains
this in plain language, and the device detail pane says so again for any device it applies to.

The full catalogue is **79 protocols** across 10 families (59 directly scannable, 20 hub-only) — IP/network, wireless PAN and mesh,
LPWAN, sub-GHz RF, infrared, powerline, wired fieldbus, vendor LAN protocols, cloud ecosystems
and proximity.

## Homey Pro integration

Local network only. No Athom cloud account, nothing about your home leaves your home, and
control keeps working when the internet is down.

1. On your Homey: **Settings → General → API Keys → New API Key**. Give it device and flow
   permissions.
2. In the app, open **Homey** and tap **Find Homey automatically** — it sweeps the subnet
   looking for the signature of Homey's local API.
3. Paste the token and connect.

The token is stored on-device only and is excluded from cloud backup and device transfer
(`backup_rules.xml`, `data_extraction_rules.xml`).

Once connected the app calls `http://<homey>/api/manager/...` with `Authorization: Bearer <token>`
for devices, zones, flows and system info, and writes capability values back with
`PUT .../device/<id>/capability/<capability>/`. Radio attribution comes from the settings keys
Homey's own radio managers write (`zw_node_id`, `zb_ieee_address`, `matter_node_id`), which is
harder evidence than parsing the driver URI.

## Built for the Fold 8

- **Hinge-aware two-pane layout.** `HingeAwareTwoPane` reads the real `FoldingFeature` bounds and
  splits panes *around* the crease, so no control ever lands on the fold. A plain weighted `Row`
  would happily put a button right on it.
- **Posture-aware.** Book posture splits horizontally; tabletop posture splits vertically to match
  how the device is physically standing; flat falls back to a weighted split.
- **Continuity across the fold.** Layout follows window width, not device identity, and both panes
  render the same composables — folding or unfolding mid-task changes the layout without losing a
  scroll position or a selection. Bottom bar under 600dp, navigation rail above it.
- **Everything resizable.** `resizeableActivity`, full `configChanges` handling, no orientation
  lock, no compat letterboxing, edge-to-edge with safe-drawing insets.
- **Type scale tuned for a 7.6-inch panel** — restrained display sizes, generous body line height.

## Design

Instrumentation, not pastel. The palette is signal-cyan on cool near-black, because the app is
fundamentally a radar and status has to be legible at a glance. Every semantic state — online,
stale, offline, controllable, hub-bridged — has a dedicated colour that stays stable even when
Material You dynamic colour is on. The Discover screen's radar is informative rather than
decorative: ring distance encodes signal strength, and devices with no radio reading sit on the
outer ring rather than being given an invented position.

## Building

```bash
./gradlew assembleDebug      # build
./gradlew testDebugUnitTest  # run the unit tests
```

Requires JDK 17 and the Android SDK (compileSdk 35, minSdk 26). Kotlin 2.0.21, Jetpack Compose
with Material 3, no annotation processors — dependency injection is a hand-written container and
persistence is JSON via DataStore, which keeps the build fast and the object lifetimes obvious.

## Tests

33 unit tests cover the parts where correctness is not obvious by inspection:

- **Protocol catalogue** — the direct/hub-only split is total and unambiguous, service-type and
  port lookups resolve, no duplicate service types.
- **Device merging** — four sightings of one speaker collapse to one device; transitive merging;
  specific protocols outrank generic ones; nicknames and favourites survive a re-scan; age-out and
  recovery.
- **Fingerprinting** — classification by name, vendor keyword and HomeKit accessory category;
  randomised MAC addresses are never reported as a vendor.
- **Homey mapping** — the `result` envelope, localised vs plain capability titles, capability
  values and ranges, control ordering, and radio attribution from settings over driver URI.
- **Subnet maths** — `/24` sweeps exclude network and broadcast addresses, `/16` sweeps are capped.
- **Serialization** — the device store round-trips every capability value shape.

## Project layout

```
core/model/       Protocol catalogue (79 protocols), Device, Capability, Observation
discovery/        DiscoveryEngine, DeviceMerger, NetworkEnvironment
  scanners/       mDNS, SSDP, UDP probe, BLE, network sweep
  fingerprint/    OUI database, Bluetooth company IDs, Fingerprinter
homey/            Local Web API client, models, device mapper, repository
data/             Settings (DataStore), device store (JSON), unified DeviceRepository
ui/
  adaptive/       FoldState, HingeAwareTwoPane
  components/     DeviceCard, RadarSweep, CapabilityControl, protocol chips, status pills
  screens/        Discover, Devices (list-detail), Protocols, Homey, Settings
  theme/          Palette, semantic status colours, type scale
```
