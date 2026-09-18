/**
 * Rasterise the reference illustrations. Chromium through Playwright, because
 * it is the renderer the SVGs were drawn against and the one already installed
 * in this environment.
 *
 *   node scripts/render_reference_art.mjs scripts/reference_art/svg scripts/reference_art
 *
 * Set CHROMIUM_PATH if Playwright cannot find a browser of its own, and
 * NODE_PATH if Playwright itself is installed globally.
 */
import { createRequire } from 'node:module';
import { readdirSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';

// require rather than import, so a globally installed Playwright on NODE_PATH
// resolves. ESM ignores NODE_PATH; CommonJS does not.
const { chromium } = createRequire(import.meta.url)('playwright');

const [dir, out] = process.argv.slice(2).map((p) => resolve(p));
const executablePath = process.env.CHROMIUM_PATH || undefined;

const browser = await chromium.launch(executablePath ? { executablePath } : {});
const page = await browser.newPage({
  viewport: { width: 900, height: 675 },
  deviceScaleFactor: 2,
});
for (const f of readdirSync(dir).filter((f) => f.endsWith('.svg'))) {
  await page.goto('file://' + join(dir, f));
  await page.screenshot({ path: join(out, basename(f, '.svg') + '.png') });
}
await browser.close();
console.log('rendered');
