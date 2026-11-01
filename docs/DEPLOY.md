# Deploying the launcher to an LG webOS TV (2022+)

Do this from a PC on the same network as the TV.

1. **Enable Developer Mode on the TV**
   - Create a free LG developer account, install the *Developer Mode* app from the LG Content Store.
   - Sign in, switch on *Dev Mode Status* and *Key Server*, and reboot. Note the TV's IP.
   - The session expires every ~50 h unless you extend it in the app (rooting removes this limit, see BLOATWARE.md).
2. **Install the CLI**: `npm i -g @webos-tools/cli` (provides `ares-*`).
3. **Register the TV**: `ares-setup-device` (add as `lgtv`, host = TV IP, port 9922, user `prisoner`), then `ares-novacom --device lgtv --getkey` and enter the passphrase shown in the Developer Mode app.
4. **Optional, recommended**: copy `webOSTV.js` from the webOS TV SDK (webOSTVjs) into `launcher/`. It provides `webOS.service.request`, which the launcher uses to open apps. Without it, tiles only show a message.
5. **Package, install, launch**
   ```
   ares-package launcher
   ares-install --device lgtv com.hyperscale.command_1.0.0_all.ipk
   ares-launch  --device lgtv com.hyperscale.command
   ```
6. **Find real app IDs**: `ares-device -i lgtv --list-apps` (or `luna-send` once rooted), then edit `launcher/apps.json` and reinstall.

## Making it your home screen
Stock webOS can't replace the home launcher. Without root, press the Home button, then pick *Command* (pin it first in the app row). With root, see BLOATWARE.md for auto-start.
