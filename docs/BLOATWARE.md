# Cleaning up LG webOS bloat

Levels, safest first. Menu names vary a little by firmware.

## 1. Settings only (no risk)
- *Settings > All Settings > General > System > Additional Settings*: turn off **Home Promotion**, **Live Plus**, **Home Hub** ads, **Content Recommendations**.
- *General > Privacy / User Agreements*: turn off **Viewing Information**, **Interest-Based & Cross-Device Advertising**, **Voice Information**; decline Live Plus.
- *Support > Eco/Energy*: nothing needed. Disable **Quick Start+** only if it causes issues.
- Home row: long-press OK on an app, then Edit to move or remove what's removable.
- Stop it phoning home: block `*.lgtvsdp.com`, `*.lgsmartad.com`, `*.lgappstv.com` at your router/Pi-hole (this can break the LG Content Store and updates).

## 2. Hide with the launcher
`launcher/apps.json` shows only the apps you list. The stock home screen is still reachable with the Home button.

## 3. Root and remove (advanced, at your own risk)
Rooting is done with the community **webOS Homebrew** project. It can void your warranty and, if done wrong, brick the TV. It only works on firmware versions not yet patched, so **do not update the TV firmware** before checking.

1. Read the official guide first: <https://www.webosbrew.org/rooting/> (and the "Dejavuln" / "Rootmy.tv" pages it links) and confirm your exact model and firmware is supported.
2. Install the **Homebrew Channel** and its on-TV root/ssh as the guide describes. Rooting steps change per firmware, so follow the current guide rather than anything copied here.
3. Once rooted, SSH in (`ssh root@<tv-ip>`) and inspect installed apps:
   ```
   luna-send -n 1 luna://com.webos.service.applicationmanager/dev/listApps '{}'
   ```
4. Back up before removing anything (`/mnt/otycabi/preload/` and the app dirs under `/usr/palm/applications` are the usual places). Prefer **disabling**/hiding over deleting where possible. Some apps (Settings, Input, Live TV, Home) are required: removing them can soft-brick the TV.
5. Disable OTA firmware updates, otherwise an update can re-add apps or remove root (the Homebrew Channel has an option for this).

I don't remove or list system app IDs here on purpose: which are safe to delete varies by model/firmware, so decide after you've listed them on your own TV.
