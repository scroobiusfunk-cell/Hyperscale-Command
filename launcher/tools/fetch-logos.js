#!/usr/bin/env node
// Downloads brand logos (Simple Icons, CC0 SVGs) into launcher/logos/ and recolors them white.
// Run on YOUR machine:  node launcher/tools/fetch-logos.js
// Logos stay out of git (see .gitignore). They're trademarks of their owners; use for your own TV.
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const cfg = JSON.parse(fs.readFileSync(path.join(root, 'apps.json'), 'utf8'));
const BASE = process.env.LOGO_BASE || 'https://cdn.jsdelivr.net/npm/simple-icons@13.21.0/icons';
const outDir = path.join(root, 'logos');
fs.mkdirSync(outDir, { recursive: true });

(async () => {
  let ok = 0, fail = 0;
  for (const app of cfg.apps) {
    if (!app.logoSlug) continue;
    const url = `${BASE}/${app.logoSlug}.svg`;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      let svg = await res.text();
      if (!/<svg[\s>]/.test(svg)) throw new Error('not an SVG');
      svg = svg.replace(/<svg\b/, '<svg fill="#ffffff"');
      fs.writeFileSync(path.join(outDir, app.logoSlug + '.svg'), svg);
      console.log('ok  ', app.name, '->', `logos/${app.logoSlug}.svg`);
      ok++;
    } catch (e) {
      console.log('FAIL', app.name, `(${app.logoSlug}): ${e.message}`);
      fail++;
    }
  }
  console.log(`\n${ok} downloaded, ${fail} failed. Apps without a logo keep their generated cover.`);
  process.exit(fail ? 1 : 0);
})();
