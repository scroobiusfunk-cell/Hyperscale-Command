// Shared helpers: load every note in the vault with its frontmatter and resolved wikilinks.
// Skips dot folders and _meta. No dependencies.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, basename } from 'node:path';

// Minimal YAML frontmatter reader: `key: value`, `key: [a, b]`, quoted strings. Enough for this vault.
export function parseFrontmatter(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  const fm = {};
  if (!m) return { fm, body: text };
  for (const line of m[1].split(/\r?\n/)) {
    const k = line.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
    if (!k) continue;
    let v = k[2].trim();
    const q = v.match(/^(["'])(.*)\1/);                              // quoted: take what's inside the quotes
    if (q) v = q[2];
    else {
      v = v.replace(/\s+#.*$/, '').trim();                           // unquoted: drop a trailing "  # comment"
      if (/^\[.*\]$/.test(v)) v = v.slice(1, -1).split(',').map(s => s.trim().replace(/^["']|["']$/g, '')).filter(Boolean);
    }
    fm[k[1]] = v;
  }
  return { fm, body: text.slice(m[0].length) };
}

export const LINK_RE = /\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]/g;

export function loadVault(vault) {
  const files = [];
  (function walk(d) {
    for (const n of readdirSync(d)) {
      if (n.startsWith('.') || n === '_meta') continue;
      const p = join(d, n);
      const st = statSync(p);
      if (st.isDirectory()) walk(p); else if (n.endsWith('.md')) files.push({ p, st });
    }
  })(vault);
  const notes = files.map(({ p, st }) => {
    const text = readFileSync(p, 'utf8');
    const id = relative(vault, p).replace(/\\/g, '/').replace(/\.md$/, '');
    const { fm, body } = parseFrontmatter(text);
    return { id, path: p, text, body, fm, title: fm.title || basename(id), mtime: st.mtimeMs, links: [] };
  });
  const byId = new Map(notes.map(n => [n.id.toLowerCase(), n]));
  const byBase = new Map();
  for (const n of notes) { const b = basename(n.id).toLowerCase(); if (!byBase.has(b)) byBase.set(b, n); }
  const resolve = target => {
    const t = target.trim().replace(/\\$/, '').replace(/\.md$/, '').toLowerCase();   // "\|" alias pipe inside tables
    return byId.get(t) || byBase.get(basename(t));
  };
  for (const n of notes) {
    const out = new Set();
    for (const m of n.body.matchAll(LINK_RE)) { const hit = resolve(m[1]); if (hit && hit !== n) out.add(hit); }
    if (typeof n.fm.project === 'string') { const pm = n.fm.project.match(/\[\[([^\]|#]+)/); const hit = pm && resolve(pm[1]); if (hit) out.add(hit); }
    n.links = [...out];
  }
  for (const n of notes) n.backlinks = [];
  for (const n of notes) for (const t of n.links) t.backlinks.push(n);
  return { notes, resolve };
}

// A note's own date: frontmatter `date`, then a YYYY-MM-DD in its name, then frontmatter `modified`.
export function noteDate(n) {
  const iso = s => (typeof s === 'string' && /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : '');
  return iso(n.fm.date) || (n.id.match(/\d{4}-\d{2}-\d{2}/) || [''])[0] || iso(n.fm.modified);
}

// Notes the tools write themselves (reviews, indexes, rollup pages). They must never count as real activity.
export const isGenerated = n => n.id.startsWith('Reviews/') || ['review', 'moc', 'index'].includes(n.fm.type);

// For each People/ note: the most recent dated note linking to (or linked from) them, and how long ago.
// Generated notes are ignored, or each weekly review (which lists stale people) would reset their flag.
export function peopleCheckins(notes, today, staleDays = 60) {
  return notes.filter(n => n.id.startsWith('People/') && n.fm.self !== 'true').map(p => {   // `self: true` = the vault owner
    const dated = [...p.backlinks, ...p.links].filter(n => !n.id.startsWith('People/') && !isGenerated(n) && noteDate(n))
      .sort((a, b) => noteDate(b).localeCompare(noteDate(a)));
    const last = dated[0] || null, days = last ? daysBetween(noteDate(last), today) : null;
    return { person: p, last, days, stale: days === null || days > staleDays };
  }).sort((a, b) => (b.days ?? 1e9) - (a.days ?? 1e9));
}

// Flashcards: one card per line "question :: answer" in notes under Flashcards/. Key = deck id + question.
export function flashcards(notes) {
  const cards = [];
  for (const n of notes.filter(n => n.id.startsWith('Flashcards/'))) {
    for (const line of n.body.split(/\r?\n/)) {
      const m = line.match(/^\s*(?:[-*]\s+)?(.+?)\s+::\s+(.+?)\s*$/);
      if (m) cards.push({ key: `${n.id}::${m[1]}`, deck: n.id, q: m[1], a: m[2] });
    }
  }
  return cards;
}

export const link = n => `[[${n.id}|${String(n.title).replace(/[|\]]/g, '-')}]]`;
export const localToday = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };
export const daysBetween = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 864e5);
