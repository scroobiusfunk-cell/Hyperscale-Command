#!/usr/bin/env node
// Builds "Second Brain Galaxy.html" (animated brain/galaxy view of this vault) outside Obsidian.
// The Obsidian plugin builds the same data live; this is the standalone fallback copy.
// Usage: node _meta/tools/build-brain-galaxy.mjs [vaultDir]
// Output stays in the vault. It contains note titles and summaries, so never commit it to the public repo.
import { readFileSync, writeFileSync } from 'node:fs';
import { join, basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadVault, noteDate } from './vault-notes.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const vault = resolve(process.argv[2] || join(here, '..', '..'));
// Same order as .obsidian/graph.json and the plugin, so colours match everywhere.
const AREA_ORDER = ['Index', 'Library', 'Meetings', 'Orgs', 'People', 'Personal', 'Projects', 'Topics', 'Training', 'White Papers', 'Work'];

const { notes } = loadVault(vault);
const index = new Map(notes.map((n, i) => [n, i]));
const seen = new Set(), edges = [], adj = notes.map(() => []);
notes.forEach((n, i) => {
  for (const t of n.links) {
    const j = index.get(t), a = Math.min(i, j), b = Math.max(i, j), k = a + ',' + b;
    if (!seen.has(k)) { seen.add(k); edges.push([a, b]); adj[a].push(b); adj[b].push(a); }
  }
});

// Same rules as the plugin; without Obsidian there is no open history, so "seen" is the note's own date.
const nodes = notes.map(n => {
  const own = noteDate(n);
  return { id: n.id, title: String(n.title), area: String(n.fm.area || 'Unsorted'), summary: String(n.fm.summary || ''),
    born: own, seen: own ? Date.parse(own) : 0, own: !!own };
});
nodes.forEach((n, i) => {
  if (n.own) return;
  const dated = adj[i].map(j => nodes[j]).filter(m => m.own);
  if (dated.length) n.born = dated.map(m => m.born).sort()[0];
  n.seen = Math.max(n.seen, ...dated.map(m => m.seen), 0);
});
nodes.forEach(n => delete n.own);
const constellations = [];
notes.forEach((n, i) => {
  if (!/^Projects\/[^/]+$/.test(n.id)) return;
  const members = [i, ...adj[i].slice().sort((a, b) => adj[b].length - adj[a].length).slice(0, 6)];
  if (members.length >= 3) constellations.push({ name: nodes[i].title, members });
});

const areas = [...AREA_ORDER, ...new Set(nodes.map(n => n.area).filter(a => !AREA_ORDER.includes(a)))];
const data = { vault: basename(vault), areas, nodes, edges, constellations, now: Date.now() };
const json = JSON.stringify(data).replace(/</g, '\\u003c');
const tpl = readFileSync(join(here, 'brain-galaxy.template.html'), 'utf8');
if (!tpl.includes('/*__DATA__*/null')) throw new Error('template is missing the /*__DATA__*/null placeholder');
const out = join(vault, 'Second Brain Galaxy.html');
writeFileSync(out, tpl.replace('/*__DATA__*/null', () => json), 'utf8');
console.log(`${nodes.length} notes, ${edges.length} synapses, ${constellations.length} constellations -> ${out}`);
// The neural-brain view uses the same data and placeholder.
try {
  const neural = readFileSync(join(here, 'brain-neural.template.html'), 'utf8');
  if (!neural.includes('/*__DATA__*/null')) throw new Error('neural template is missing the /*__DATA__*/null placeholder');
  const outN = join(vault, 'Second Brain Neural.html');
  writeFileSync(outN, neural.replace('/*__DATA__*/null', () => json), 'utf8');
  console.log(`neural brain -> ${outN}`);
} catch (e) { if (e.code !== 'ENOENT') throw e; }
