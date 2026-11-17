#!/usr/bin/env node
// Usage: node build-index.mjs <vaultDir> <out.json>
// Walks a vault of .md files and writes the JSON the viewer loads (notes, edges, backlinks).
import { readdirSync, readFileSync, statSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { buildIndex } from './vault-lib.mjs';

const [vault, out] = process.argv.slice(2);
if (!vault || !out) { console.error('usage: build-index.mjs <vaultDir> <out.json>'); process.exit(2); }

const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    if (name.startsWith('.')) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (name.toLowerCase().endsWith('.md')) files.push({ path: relative(vault, p), text: readFileSync(p, 'utf8') });
  }
})(vault);

const index = buildIndex(files);
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(index));
console.log(`${index.notes.length} notes, ${index.edges.length} links, ${index.broken.length} broken -> ${out}`);
