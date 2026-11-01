# Hyperscale-Command

A fast, glassy launcher for LG webOS TVs (2022+) with live weather and news, plus notes on removing bloatware.

- `launcher/`: the webOS web app (edit `apps.json`)
- `docs/DEPLOY.md`: install it on your TV
- `docs/BLOATWARE.md`: settings cleanup and root-and-remove walkthrough

## Remote controls

| Button | Action |
| --- | --- |
| Arrows | Move between apps. Down from the bottom row reaches the news bar |
| Left / Right on the news bar | Previous / next headline |
| OK | Open the app (or the headline, in the TV browser) |
| Red | Performance mode: Auto → Full glass → Lite |
| Yellow | Open the current headline |
| Blue | Ambient screen now (it also appears after `idleSeconds` of no input) |
| Back | Leave the launcher |

The launcher reopens on the app you last used.

## Settings (`launcher/apps.json` → `settings`)

- `weather.location`: city name (looked up once via Open-Meteo, no API key). Or set `lat`/`lon`. `units`: `celsius` or `fahrenheit`.
- `news.feeds`: any RSS/Atom URLs. `rotateSeconds`, `max`.
- `idleSeconds`: seconds before the ambient screen (0 turns it off).
- `corsProxy`: only if your TV refuses direct feed requests (see DEPLOY.md).

## Performance

Animations only use transform and opacity; glows are pre-painted and faded. In **Auto**, the launcher measures frame times
during your first few button presses and switches itself to **Lite** (no backdrop blur or refraction) if the TV can't keep up.
Weather and news are cached, so the screen is filled instantly on boot and refreshed in the background.
