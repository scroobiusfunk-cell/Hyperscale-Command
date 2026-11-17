import { useEffect, useMemo, useRef, useState } from 'react';
import MiniSearch from 'minisearch';
import { marked } from 'marked';
import { forceCenter, forceLink, forceManyBody, forceSimulation, forceCollide } from 'd3-force';
import { buildIndex, makeResolver, type Note, type VaultIndex } from '../../tools/vault-lib.mjs';

const hashId = () => decodeURIComponent(location.hash.replace(/^#\/?note\//, '')) || '';

function sanitize(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('script,iframe,object,embed,style,link,meta').forEach(n => n.remove());
  doc.querySelectorAll('*').forEach(el => {
    for (const a of [...el.attributes]) {
      if (/^on/i.test(a.name) || (/^(href|src)$/i.test(a.name) && /^\s*javascript:/i.test(a.value))) el.removeAttribute(a.name);
    }
  });
  return doc.body.innerHTML;
}

function renderNote(note: Note, resolve: (t: string) => Note | null): string {
  const body = note.body.replace(/^\s*#\s+.+\r?\n/, '');
  const withLinks = body.replace(/\[\[([^\]\n|#]+)(?:#([^\]\n|]+))?(?:\|([^\]\n]+))?\]\]/g, (_m, target: string, _h, alias?: string) => {
    const hit = resolve(target.trim());
    const label = (alias || hit?.title || target).replace(/[<>&"]/g, c => `&#${c.charCodeAt(0)};`);
    return hit
      ? `<a class="wiki" href="#/note/${encodeURIComponent(hit.id)}">${label}</a>`
      : `<a class="wiki missing" title="No such note">${label}</a>`;
  });
  return sanitize(marked.parse(withLinks, { async: false }) as string);
}

async function readFolder(files: FileList): Promise<VaultIndex> {
  const md = [...files].filter(f => /\.md$/i.test(f.name));
  const rel = (f: File) => ((f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name).split('/').slice(1).join('/') || f.name;
  const list = await Promise.all(md.map(async f => ({ path: rel(f), text: await f.text() })));
  return buildIndex(list);
}

function Graph({ index, current, onOpen }: { index: VaultIndex; current: string; onOpen: (id: string) => void }) {
  const [pos, setPos] = useState<Record<string, { x: number; y: number }>>({});
  const ref = useRef<SVGSVGElement>(null);
  const W = 900, H = 640;
  const areas = useMemo(() => [...new Set(index.notes.map(n => n.area))], [index]);
  useEffect(() => {
    const nodes = index.notes.map(n => ({ id: n.id }));
    const links = index.edges.map(e => ({ source: e.source, target: e.target }));
    const sim = forceSimulation(nodes as { id: string; x?: number; y?: number }[])
      .force('link', forceLink(links).id((d: any) => d.id).distance(40).strength(0.4))
      .force('charge', forceManyBody().strength(-60))
      .force('center', forceCenter(W / 2, H / 2))
      .force('collide', forceCollide(8))
      .stop();
    const ticks = Math.min(300, 60 + Math.ceil(nodes.length / 4));
    for (let i = 0; i < ticks; i++) sim.tick();
    const p: Record<string, { x: number; y: number }> = {};
    for (const n of nodes as { id: string; x: number; y: number }[]) p[n.id] = { x: Math.max(10, Math.min(W - 10, n.x)), y: Math.max(10, Math.min(H - 10, n.y)) };
    setPos(p);
  }, [index]);
  const deg = (id: string) => (index.backlinks[id]?.length || 0) + index.edges.filter(e => e.source === id).length;
  const hue = (a: string) => `hsl(${(areas.indexOf(a) * 67 + 205) % 360} 40% 45%)`;
  return (
    <svg ref={ref} className="graph" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Note graph">
      {index.edges.map(e => pos[e.source] && pos[e.target] && (
        <line key={e.source + e.target} x1={pos[e.source].x} y1={pos[e.source].y} x2={pos[e.target].x} y2={pos[e.target].y} stroke="var(--color-divider)" />
      ))}
      {index.notes.map(n => pos[n.id] && (
        <g key={n.id} transform={`translate(${pos[n.id].x},${pos[n.id].y})`} style={{ cursor: 'pointer' }} onClick={() => onOpen(n.id)}>
          <circle r={Math.min(14, 4 + deg(n.id))} fill={hue(n.area)} stroke={n.id === current ? 'var(--color-text)' : 'none'} strokeWidth={2} />
          <title>{n.title}</title>
          {(index.notes.length < 80 || deg(n.id) > 4 || n.id === current) && <text x={8} y={3}>{n.title.slice(0, 28)}</text>}
        </g>
      ))}
    </svg>
  );
}

export default function App() {
  const [index, setIndex] = useState<VaultIndex | null>(null);
  const [err, setErr] = useState('');
  const [q, setQ] = useState('');
  const [area, setArea] = useState('All');
  const [tag, setTag] = useState('');
  const [view, setView] = useState<'note' | 'graph'>('note');
  const [id, setId] = useState(hashId());

  useEffect(() => {
    fetch('./vault.json').then(r => (r.ok ? r.json() : Promise.reject(new Error('no vault.json')))).then(setIndex).catch(() => setErr('No indexed vault found. Open your vault folder below.'));
    const onHash = () => setId(hashId());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const resolve = useMemo(() => (index ? makeResolver(index.notes) : () => null), [index]);
  const byId = useMemo(() => new Map((index?.notes || []).map(n => [n.id, n])), [index]);
  const search = useMemo(() => {
    if (!index) return null;
    const ms = new MiniSearch({ fields: ['title', 'summary', 'body', 'tagsText'], storeFields: [], searchOptions: { prefix: true, fuzzy: 0.15, boost: { title: 3, summary: 2 } } });
    ms.addAll(index.notes.map(n => ({ id: n.id, title: n.title, summary: n.summary, body: n.body, tagsText: n.tags.join(' ') })));
    return ms;
  }, [index]);

  const areas = useMemo(() => ['All', ...[...new Set((index?.notes || []).map(n => n.area))].sort()], [index]);
  const tags = useMemo(() => {
    const c = new Map<string, number>();
    for (const n of index?.notes || []) for (const t of n.tags) c.set(t, (c.get(t) || 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1]).slice(0, 24);
  }, [index]);

  const results = useMemo(() => {
    if (!index) return [];
    let notes: Note[] = q.trim() && search ? search.search(q).map(r => byId.get(r.id as string)!).filter(Boolean) : [...index.notes].sort((a, b) => a.title.localeCompare(b.title));
    if (area !== 'All') notes = notes.filter(n => n.area === area);
    if (tag) notes = notes.filter(n => n.tags.includes(tag));
    return notes.slice(0, 200);
  }, [index, q, search, area, tag, byId]);

  const note = byId.get(id) || (index ? byId.get('00-Index') || index.notes[0] : undefined);
  const html = useMemo(() => (note ? renderNote(note, resolve) : ''), [note, resolve]);
  const open = (nid: string) => { location.hash = `#/note/${encodeURIComponent(nid)}`; setView('note'); };

  if (!index) {
    return (
      <div className="main" style={{ maxWidth: 560, margin: '0 auto' }}>
        <div className="brand">Second Brain</div>
        <p className="empty">{err || 'Loading…'}</p>
        <label className="drop">
          Choose your vault folder (reads .md files locally in your browser; nothing is uploaded)
          <input type="file" style={{ display: 'none' }} {...({ webkitdirectory: '', directory: '' } as object)} multiple
            onChange={async e => e.target.files && setIndex(await readFolder(e.target.files))} />
        </label>
      </div>
    );
  }

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">Second Brain</div>
        <input className="input search" type="search" placeholder={`Search ${index.notes.length} notes…`} value={q} onChange={e => setQ(e.target.value)} aria-label="Search notes" />
        <div className="row">
          {areas.map(a => <button key={a} className={`btn chip ${area === a ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setArea(a)}>{a}</button>)}
        </div>
        <div className="row">
          {tags.map(([t, c]) => <button key={t} className={`tag ${tag === t ? 'tag-accent' : 'tag-neutral'}`} style={{ border: 'none', cursor: 'pointer' }} onClick={() => setTag(tag === t ? '' : t)}>#{t} {c}</button>)}
        </div>
        <div className="list">
          {results.map(n => (
            <button key={n.id} className="item" aria-current={n.id === note?.id} onClick={() => open(n.id)}>
              <span className="m">{n.area}{n.type ? ` · ${n.type}` : ''}</span>
              <span className="t">{n.title}</span>
              {n.summary && <span className="s">{n.summary}</span>}
            </button>
          ))}
          {results.length === 0 && <p className="empty">No notes match.</p>}
        </div>
      </aside>

      <main className="main" onClick={e => { const a = (e.target as HTMLElement).closest('a.wiki.missing'); if (a) e.preventDefault(); }}>
        <div className="tabs">
          <button className={`btn ${view === 'note' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setView('note')}>Note</button>
          <button className={`btn ${view === 'graph' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setView('graph')}>Graph</button>
        </div>
        {view === 'graph' ? <Graph index={index} current={note?.id || ''} onOpen={open} /> : note ? (
          <article className="note">
            <div className="meta">
              <span className="tag tag-accent">{note.area}</span>
              {note.type && <span className="tag tag-neutral">{note.type}</span>}
              {note.modified && <span className="empty">Modified {note.modified}</span>}
              {note.source && /^https?:/.test(note.source) && <a href={note.source} target="_blank" rel="noreferrer noopener">Open in Drive ↗</a>}
            </div>
            <h1>{note.title}</h1>
            <div dangerouslySetInnerHTML={{ __html: html }} />
          </article>
        ) : <p className="empty">Empty vault.</p>}
      </main>

      <aside className="right">
        <div className="k">Backlinks</div>
        <div className="list">
          {(note && index.backlinks[note.id] || []).map(b => byId.get(b)).filter(Boolean).map(n => (
            <button key={n!.id} className="item" onClick={() => open(n!.id)}><span className="t">{n!.title}</span><span className="m">{n!.area}</span></button>
          ))}
          {note && !(index.backlinks[note.id] || []).length && <p className="empty">None yet.</p>}
        </div>
        <div className="k">Tags</div>
        <div className="row">{note?.tags.map(t => <button key={t} className="tag tag-neutral" style={{ border: 'none', cursor: 'pointer' }} onClick={() => setTag(t)}>#{t}</button>)}</div>
        {index.broken.length > 0 && <div className="empty">{index.broken.length} unresolved links in vault.</div>}
      </aside>
    </div>
  );
}
