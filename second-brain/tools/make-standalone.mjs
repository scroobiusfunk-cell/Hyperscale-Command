#!/usr/bin/env node
// Usage: node make-standalone.mjs <viewer/dist> <vault.json> <out.html>
// Inlines JS, CSS and the vault index into ONE html file that works by double-click (file://), offline.
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const [dist, vaultJson, out] = process.argv.slice(2);
if (!out) { console.error('usage: make-standalone.mjs <dist> <vault.json> <out.html>'); process.exit(2); }
let html = readFileSync(join(dist, 'index.html'), 'utf8');
const safe = s => s.replace(/<\/(script|style)/gi, '<\\/$1');
html = html.replace(/<link[^>]+rel="stylesheet"[^>]*href="([^"]+)"[^>]*>/g, (_m, h) => `<style>${safe(readFileSync(join(dist, h), 'utf8'))}</style>`);
const vault = safe(readFileSync(vaultJson, 'utf8'));
let js = '';
html = html.replace(/<script[^>]+src="([^"]+)"[^>]*><\/script>/g, (_m, s) => { js += safe(readFileSync(join(dist, s), 'utf8')); return ''; });
html = html.replace('</body>', () => `<script>window.__VAULT__=${vault};</script><script type="module">${js}</script></body>`);
writeFileSync(out, html);
console.log(`wrote ${out} (${(html.length / 1024).toFixed(0)} KB)`);
