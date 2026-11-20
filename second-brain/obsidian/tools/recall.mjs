#!/usr/bin/env node
// Recall: instant lookup over the vault, built for Claude (works for you too).
//
//   node _meta/tools/recall.mjs "inspection level owner"   ranked notes, summary, best matching line, links
//   node _meta/tools/recall.mjs "rfi generator" --n 15 --json more hits, machine-readable
//   node _meta/tools/recall.mjs --links "People/Sample Person" a note's outgoing links and backlinks
//   node _meta/tools/recall.mjs --build                     force a rebuild (also writes _meta/Brain Map.md)
//
// The index (_meta/recall-index.json) is rebuilt by itself whenever any note changes, so it is never stale.
// Ranking is BM25F: title and aliases count most, then tags and summary, then headings, then body text.
// Unknown words fall back to prefix matches, then one-typo matches; _meta/recall-synonyms.json adds synonyms.
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync, mkdirSync } from 'node:fs';
import { join, dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadVault, noteDate } from './vault-notes.mjs';

// The vault is two folders up (<vault>/_meta/tools), or set SECOND_BRAIN_VAULT to point elsewhere.
const VAULT = resolve(process.env.SECOND_BRAIN_VAULT || join(dirname(fileURLToPath(import.meta.url)), '..', '..'));
const INDEX = join(VAULT, '_meta', 'recall-index.json');
const MAP = join(VAULT, '_meta', 'Brain Map.md');
const SYN = join(VAULT, '_meta', 'recall-synonyms.json');
const VERSION = 2;
const FIELDS = { title: 4, aliases: 4, tags: 2.5, summary: 2.5, headings: 1.5, body: 1 };   // field weights
const B = { title: .3, aliases: .3, tags: .2, summary: .5, headings: .6, body: .75 };      // length normalisation per field
const K1 = 1.2;

// ---------- text ----------
const STOP = new Set('a an and are as at be by for from has have in into is it its of on or that the this to was were will with not no but can all any our your their its'.split(' '));
const stem = t => (t.length > 4 && t.endsWith('ies') ? t.slice(0, -3) + 'y' : t.length > 3 && t.endsWith('s') && !t.endsWith('ss') && !t.endsWith('us') ? t.slice(0, -1) : t);
export function tokens(text) {
  const out = [];
  for (const raw of String(text).toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').match(/[a-z0-9]+(?:[-.'][a-z0-9]+)*/g) || []) {
    const parts = raw.split(/[-.']/);
    for (const p of parts) if (p && !STOP.has(p)) out.push(stem(p));
    if (parts.length > 1 && raw.length <= 24) out.push(parts.join(''));            // "bp-02" also as "bp02", "s7117" stays
  }
  return out;
}
const fieldText = n => {
  const al = n.fm.aliases ?? n.fm.alias ?? [];
  const tags = n.fm.tags ?? [];
  const body = n.body.replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, '$2').replace(/\[\[([^\]]+)\]\]/g, '$1').replace(/<!--[\s\S]*?-->/g, ' ');
  return {
    title: `${n.title} ${n.id.split('/').pop()}`,
    aliases: Array.isArray(al) ? al.join(' ') : al,
    tags: Array.isArray(tags) ? tags.join(' ') : tags,
    summary: n.fm.summary || '',
    headings: (body.match(/^#{1,6} .*$/gm) || []).join(' '),
    body,
  };
};

// ---------- freshness: a cheap signature of every note's path and mtime ----------
function signature() {
  let count = 0, sum = 0, max = 0;
  (function walk(d) {
    for (const n of readdirSync(d)) {
      if (n.startsWith('.') || n === '_meta') continue;
      const p = join(d, n), st = statSync(p);
      if (st.isDirectory()) walk(p);
      else if (n.endsWith('.md')) { count++; sum = (sum + st.mtimeMs + p.length * 7919) % 1e15; max = Math.max(max, st.mtimeMs); }
    }
  })(VAULT);
  return `${VERSION}:${count}:${Math.round(max)}:${Math.round(sum)}`;
}

// ---------- build ----------
export function build(sig = signature()) {
  const { notes } = loadVault(VAULT);
  const docs = [], postings = {}, lens = Object.fromEntries(Object.keys(FIELDS).map(f => [f, []]));
  const tfs = notes.map(n => {
    const ft = fieldText(n), per = {};
    for (const f of Object.keys(FIELDS)) {
      const toks = tokens(ft[f]); lens[f].push(toks.length);
      const c = per[f] = new Map(); for (const t of toks) c.set(t, (c.get(t) || 0) + 1);
    }
    return per;
  });
  const avg = Object.fromEntries(Object.keys(FIELDS).map(f => [f, Math.max(1, lens[f].reduce((a, b) => a + b, 0) / lens[f].length)]));
  notes.forEach((n, i) => {
    docs.push({
      id: n.id, title: n.title, type: n.fm.type || '', area: n.fm.area || '', status: n.fm.status || '', date: noteDate(n),
      summary: n.fm.summary || '', out: n.links.map(l => l.id), back: n.backlinks.map(l => l.id),
    });
    const w = new Map();                                                    // BM25F: one weighted, normalised tf per term
    for (const f of Object.keys(FIELDS)) {
      const norm = 1 - B[f] + B[f] * (lens[f][i] / avg[f]);
      for (const [t, c] of tfs[i][f]) w.set(t, (w.get(t) || 0) + FIELDS[f] * c / norm);
    }
    for (const [t, v] of w) (postings[t] ||= []).push([i, Math.round(v * 100) / 100]);
  });
  const index = { sig, built: new Date().toISOString(), N: docs.length, docs, postings };
  mkdirSync(dirname(INDEX), { recursive: true });
  writeFileSync(INDEX, JSON.stringify(index));
  writeBrainMap(docs);
  return index;
}

// One file with every note on one line, grouped by folder: a whole-vault overview in a single read.
function writeBrainMap(docs) {
  const groups = new Map();
  for (const d of docs) { const g = d.id.includes('/') ? d.id.split('/')[0] : '(top)'; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(d); }
  const lines = ['# Brain Map', '', `Every note in the vault, one line each (${docs.length} notes). Generated by \`_meta/tools/recall.mjs\`; do not edit.`,
    'Format: path · type/status · date · summary · links in/out.', ''];
  for (const [g, list] of [...groups].sort((a, b) => a[0].localeCompare(b[0]))) {
    lines.push(`## ${g} (${list.length})`);
    for (const d of list.sort((a, b) => a.id.localeCompare(b.id))) {
      const meta = [d.type, d.status].filter(Boolean).join('/');
      lines.push(`- ${d.id}${meta ? ` · ${meta}` : ''}${d.date ? ` · ${d.date}` : ''} · ${d.summary || '(no summary)'} · ${d.back.length}↙ ${d.out.length}↗`);
    }
    lines.push('');
  }
  writeFileSync(MAP, lines.join('\n'));
}

export function load({ force = false } = {}) {
  const sig = signature();
  if (!force && existsSync(INDEX)) {
    try { const idx = JSON.parse(readFileSync(INDEX, 'utf8')); if (idx.sig === sig) return { idx, fresh: true }; } catch {}
  }
  return { idx: build(sig), fresh: false };
}

// ---------- search ----------
function edits1(a, b) {                                                     // true if a and b are at most one edit apart
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0, j = 0, e = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++e > 1) return false;
    if (a.length > b.length) i++; else if (b.length > a.length) j++; else { i++; j++; }
  }
  return e + (a.length - i) + (b.length - j) <= 1;
}
function expand(t, idx, vocab, syn) {
  const out = [];
  if (idx.postings[t]) out.push([t, 1]);
  else {
    const pre = vocab.filter(v => v.startsWith(t) && v !== t).slice(0, 12);
    if (pre.length && t.length >= 2) pre.forEach(v => out.push([v, .7]));
    else if (t.length >= 5) vocab.filter(v => edits1(t, v)).slice(0, 6).forEach(v => out.push([v, .5]));
  }
  for (const s of syn[t] || []) for (const st of tokens(s)) if (idx.postings[st]) out.push([st, .6]);
  return out;
}
export function search(query, { n = 8, idx = load().idx } = {}) {
  let syn = {};
  try { if (existsSync(SYN)) syn = Object.fromEntries(Object.entries(JSON.parse(readFileSync(SYN, 'utf8'))).map(([k, v]) => [stem(k.toLowerCase()), v])); } catch {}
  const vocab = Object.keys(idx.postings);
  const qt = [...new Set(tokens(query))];
  const scores = new Float64Array(idx.N), hits = new Uint16Array(idx.N);
  for (const t of qt) {
    const seen = new Set();
    for (const [term, w] of expand(t, idx, vocab, syn)) {
      const list = idx.postings[term], idf = Math.log(1 + (idx.N - list.length + .5) / (list.length + .5));
      for (const [d, tf] of list) {
        scores[d] += w * idf * (tf * (K1 + 1)) / (tf + K1);
        if (!seen.has(d)) { seen.add(d); hits[d]++; }
      }
    }
  }
  const phrase = query.trim().toLowerCase();
  const ranked = [];
  for (let d = 0; d < idx.N; d++) {
    if (!scores[d]) continue;
    const doc = idx.docs[d];
    let s = scores[d] * (1 + .5 * (hits[d] / qt.length) ** 2);               // reward notes that match every word
    if (phrase.length > 2 && doc.title.toLowerCase().includes(phrase)) s *= 1.6;
    else if (phrase.length > 2 && doc.summary.toLowerCase().includes(phrase)) s *= 1.25;
    s *= 1 + .04 * Math.log1p(doc.back.length);                              // well-connected notes edge ahead on ties
    ranked.push({ d, score: s });
  }
  ranked.sort((a, b) => b.score - a.score);
  return { terms: qt, total: ranked.length, results: ranked.slice(0, n).map(r => ({ ...idx.docs[r.d], score: +r.score.toFixed(2), matched: hits[r.d] })) };
}

// Best matching line of a note, read on demand (only for the hits shown).
function snippet(id, terms) {
  try {
    const text = readFileSync(join(VAULT, id + '.md'), 'utf8').replace(/^---[\s\S]*?\n---/, '');
    let best = '', bs = 0;
    for (const line of text.split(/\r?\n/)) {
      const l = line.trim(); if (l.length < 30 || l.startsWith('#') || l.startsWith('<!--')) continue;   // skip bare link-list lines
      const lt = new Set(tokens(l)); const s = terms.filter(t => [...lt].some(x => x.startsWith(t))).length;
      if (s > bs) { bs = s; best = l; }
    }
    return best.replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, '$2').replace(/\[\[([^\]]+)\]\]/g, '$1').slice(0, 180);
  } catch { return ''; }
}

// ---------- CLI ----------
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), flag = f => { const i = args.indexOf(f); if (i < 0) return null; args.splice(i, 1); return true; };
  const opt = f => { const i = args.indexOf(f); if (i < 0) return null; const v = args[i + 1]; args.splice(i, 2); return v; };
  const t0 = performance.now();
  const json = flag('--json'), force = flag('--build'), linksOf = opt('--links'), n = Number(opt('--n')) || 8;
  const { idx, fresh } = load({ force });
  if (linksOf) {
    const key = linksOf.replace(/\.md$/, '').toLowerCase();
    const doc = idx.docs.find(d => d.id.toLowerCase() === key) || idx.docs.find(d => d.title.toLowerCase() === key) || search(linksOf, { n: 1, idx }).results[0];
    if (!doc) { console.log('No such note.'); process.exit(1); }
    if (json) console.log(JSON.stringify(doc, null, 1));
    else console.log(`${doc.id}.md — ${doc.summary}\n→ links to (${doc.out.length}): ${doc.out.join(' · ') || '-'}\n← linked from (${doc.back.length}): ${doc.back.join(' · ') || '-'}`);
    process.exit(0);
  }
  const query = args.join(' ').trim();
  if (!query) { if (force) console.log(`Index rebuilt: ${idx.N} notes, ${Object.keys(idx.postings).length} terms. Brain Map written.`); else console.log('Usage: node _meta/tools/recall.mjs "<query>" [--n 8] [--json] | --links "<note>" | --build'); process.exit(0); }
  const res = search(query, { n, idx });
  if (json) { console.log(JSON.stringify({ query, ms: Math.round(performance.now() - t0), ...res }, null, 1)); process.exit(0); }
  const ms = (performance.now() - t0).toFixed(0);
  console.log(`recall "${query}" — ${res.total} matching notes, top ${res.results.length} (${ms} ms, index ${fresh ? 'fresh' : 'rebuilt'})`);
  res.results.forEach((r, k) => {
    const meta = [r.type, r.status, r.date].filter(Boolean).join(' · ');
    console.log(`\n${k + 1}. ${r.id}.md  [${meta}]  score ${r.score}${r.matched < res.terms.length ? `  (${r.matched}/${res.terms.length} words)` : ''}`);
    if (r.summary) console.log(`   ${r.summary}`);
    const sn = snippet(r.id, res.terms); if (sn && sn !== r.summary) console.log(`   > ${sn}`);
    const rel = [...new Set([...r.out, ...r.back])].filter(x => !x.startsWith('Areas/') && x !== '00-Index' && x !== 'Home').slice(0, 5);
    if (rel.length) console.log(`   links: ${rel.join(' · ')}`);
  });
  if (!res.results.length) console.log('Nothing matched. Try fewer or different words, or read _meta/Brain Map.md.');
}
