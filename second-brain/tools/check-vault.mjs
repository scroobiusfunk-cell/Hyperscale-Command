#!/usr/bin/env node
// Usage: node check-vault.mjs <vaultDir>   Exits 1 on broken wikilinks or missing required frontmatter.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { buildIndex } from './vault-lib.mjs';

const vault = process.argv[2];
if (!vault) { console.error('usage: check-vault.mjs <vaultDir>'); process.exit(2); }
const files = [];
(function walk(d) {
  for (const n of readdirSync(d)) {
    if (n.startsWith('.')) continue;
    const p = join(d, n);
    if (statSync(p).isDirectory()) walk(p); else if (n.endsWith('.md')) files.push({ path: relative(vault, p), text: readFileSync(p, 'utf8') });
  }
})(vault);
const idx = buildIndex(files);
let bad = 0;
for (const b of idx.broken) { console.log(`BROKEN  ${b.from} -> [[${b.target}]]`); bad++; }
for (const n of idx.notes) {
  for (const k of ['title', 'type', 'area']) if (!n.fm[k]) { console.log(`MISSING ${n.id}: ${k}`); bad++; }
}
const linked = new Set(idx.edges.flatMap(e => [e.source, e.target]));
const orphans = idx.notes.filter(n => !linked.has(n.id));
console.log(`${idx.notes.length} notes, ${idx.edges.length} links, ${orphans.length} orphans, ${bad} problems`);
process.exit(bad ? 1 : 0);
