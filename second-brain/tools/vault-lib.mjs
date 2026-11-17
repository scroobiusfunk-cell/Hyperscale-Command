// Shared vault parsing: used by the Node build/check tools and by the browser viewer.
// Dependency-free. Understands the Obsidian subset we write: YAML frontmatter
// (scalars, inline [a, b] lists, "- item" lists), [[wikilinks]] (with |alias and #heading), #tags.

const FM = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/;

function scalar(v) {
  v = v.trim();
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) return v.slice(1, -1);
  if (v === 'true') return true;
  if (v === 'false') return false;
  if (v === 'null' || v === '~' || v === '') return '';
  return v;
}

export function parseFrontmatter(text) {
  const m = FM.exec(text);
  if (!m) return { data: {}, body: text };
  const data = {};
  let key = null;
  for (const raw of m[1].split(/\r?\n/)) {
    const item = /^\s+-\s+(.*)$/.exec(raw);
    if (item && key) { (data[key] ||= []).push(scalar(item[1])); continue; }
    const kv = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(raw);
    if (!kv) continue;
    key = kv[1];
    const val = kv[2].trim();
    if (val.startsWith('[') && val.endsWith(']')) {
      data[key] = val.slice(1, -1).split(',').map(s => scalar(s)).filter(s => s !== '');
    } else if (val === '') {
      data[key] = [];
    } else data[key] = scalar(val);
  }
  return { data, body: text.slice(m[0].length) };
}

const WIKI = /\[\[([^\]\n|#]+)(?:#([^\]\n|]+))?(?:\|([^\]\n]+))?\]\]/g;

export function extractLinks(body) {
  const out = [];
  for (const m of body.matchAll(WIKI)) out.push({ target: m[1].trim(), heading: m[2]?.trim(), alias: m[3]?.trim() });
  return out;
}

export function extractTags(body, fm) {
  const set = new Set(Array.isArray(fm.tags) ? fm.tags : fm.tags ? [fm.tags] : []);
  for (const m of body.replace(/```[\s\S]*?```/g, '').matchAll(/(?:^|\s)#([A-Za-z][\w/-]*)/g)) set.add(m[1]);
  return [...set].map(t => String(t).replace(/^#/, ''));
}

const baseName = p => p.replace(/\\/g, '/').split('/').pop().replace(/\.md$/i, '');

export function parseNote(path, text) {
  const { data, body } = parseFrontmatter(text);
  const name = baseName(path);
  return {
    id: path.replace(/\\/g, '/').replace(/\.md$/i, ''),
    path: path.replace(/\\/g, '/'),
    name,
    title: data.title || name,
    area: data.area || path.split('/')[0],
    type: data.type || '',
    summary: data.summary || '',
    source: data.source || '',
    modified: data.modified || '',
    fm: data,
    tags: extractTags(body, data),
    body,
    links: extractLinks(body),
  };
}

/** Obsidian-style resolution: exact path, else unique basename (case-insensitive). */
export function makeResolver(notes) {
  const byId = new Map(notes.map(n => [n.id.toLowerCase(), n]));
  const byName = new Map();
  for (const n of notes) {
    const k = n.name.toLowerCase();
    (byName.get(k) || byName.set(k, []).get(k)).push(n);
  }
  return target => {
    const t = target.replace(/\.md$/i, '').toLowerCase();
    return byId.get(t) || (byName.get(t)?.length ? byName.get(t)[0] : null);
  };
}

export function buildGraph(notes) {
  const resolve = makeResolver(notes);
  const edges = [];
  const backlinks = {};
  const broken = [];
  for (const n of notes) {
    const seen = new Set();
    for (const l of n.links) {
      const t = resolve(l.target);
      if (!t) { broken.push({ from: n.id, target: l.target }); continue; }
      if (t.id === n.id || seen.has(t.id)) continue;
      seen.add(t.id);
      edges.push({ source: n.id, target: t.id });
      (backlinks[t.id] ||= []).push(n.id);
    }
  }
  return { edges, backlinks, broken };
}

export function buildIndex(files) {
  const notes = files.filter(f => /\.md$/i.test(f.path) && !/(^|\/)(\.|_meta\/)/.test(f.path)).map(f => parseNote(f.path, f.text));
  const { edges, backlinks, broken } = buildGraph(notes);
  return { notes, edges, backlinks, broken, generated: new Date().toISOString() };
}
