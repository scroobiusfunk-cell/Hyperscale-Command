// Second Brain: a tiny local plugin (no build step, no network). (Its id is still "second-brain-galaxy".)
//  - Neural Brain tab: a rotating 3D brain of your notes with synapses firing. Every time it opens (or you press
//    its reload button) it rebuilds from Obsidian's
//    own index of your notes. The page runs in an iframe sandboxed to "allow-scripts" only: it gets an opaque
//    origin, so it cannot touch Obsidian, the vault or Node. It can only postMessage {type:'sb-open', id}.
//  - Flashcards tab: spaced-repetition review of "question :: answer" lines in Flashcards/ notes.
//  - Remembers when you open each note (plugin data only), so the galaxy can dim notes you haven't visited.
const { Plugin, ItemView, Notice, TFile } = require('obsidian');

const VIEW = 'second-brain-galaxy';            // id kept from the Galaxy days, so open tabs keep working
const CARDS_VIEW = 'second-brain-flashcards';
// The tab shows the 3D Neural Brain. The old galaxy page is kept, unused, at _meta/tools/brain-galaxy.template.html.
const TEMPLATE = '_meta/tools/brain-neural.template.html';
const PREBUILT = 'Second Brain Neural.html';   // fallback if the template is missing
// Same order as .obsidian/graph.json and build-brain-galaxy.mjs, so colours match everywhere.
const AREA_ORDER = ['Index', 'Library', 'Meetings', 'Orgs', 'People', 'Personal', 'Projects', 'Topics', 'Training', 'White Papers', 'Work'];
const DAY = 864e5;

const isoDay = s => (typeof s === 'string' && /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : '');
const localToday = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };
const addDays = (ymd, n) => new Date(Date.parse(ymd + 'T12:00:00Z') + n * DAY).toISOString().slice(0, 10);

// ---- galaxy data ------------------------------------------------------------------------------------
// Build the {vault, areas, nodes, edges, constellations} data the page expects, from Obsidian's metadata cache.
//   node.born: the note's own date (frontmatter date, a date in its name, or Drive modified date);
//              hub notes without one inherit the earliest date among their neighbours.
//   node.seen: when you last opened it (ms); hubs inherit their most recently seen neighbour.
function buildData(app, opened) {
  const files = app.vault.getMarkdownFiles().filter(f => !f.path.startsWith('_meta/'));
  const index = new Map(files.map((f, i) => [f.path, i]));
  const nodes = files.map(f => {
    const fm = app.metadataCache.getFileCache(f)?.frontmatter || {};
    const own = isoDay(String(fm.date || '')) || (f.basename.match(/\d{4}-\d{2}-\d{2}/) || [''])[0] || isoDay(String(fm.modified || ''));
    return {
      id: f.path.replace(/\.md$/, ''),
      title: String(fm.title || f.basename),
      area: String(fm.area || 'Unsorted'),
      summary: fm.summary ? String(fm.summary) : '',
      born: own, seen: Math.max(opened[f.path] || 0, own ? Date.parse(own) : 0), own: !!own,
    };
  });
  const seenPairs = new Set(), edges = [], adj = nodes.map(() => []);
  for (const [src, targets] of Object.entries(app.metadataCache.resolvedLinks)) {
    const i = index.get(src);
    if (i === undefined) continue;
    for (const dst of Object.keys(targets)) {
      const j = index.get(dst);
      if (j === undefined || j === i) continue;
      const a = Math.min(i, j), b = Math.max(i, j), k = a + ',' + b;
      if (!seenPairs.has(k)) { seenPairs.add(k); edges.push([a, b]); adj[a].push(b); adj[b].push(a); }
    }
  }
  nodes.forEach((n, i) => {
    if (n.own) return;
    const dated = adj[i].map(j => nodes[j]).filter(m => m.own);
    if (dated.length) n.born = dated.map(m => m.born).sort()[0];
    n.seen = Math.max(n.seen, ...dated.map(m => m.seen), 0);
  });
  nodes.forEach(n => delete n.own);
  // One constellation per top-level project note: the project plus its 6 best-connected neighbours.
  const constellations = [];
  files.forEach((f, i) => {
    if (!/^Projects\/[^/]+\.md$/.test(f.path)) return;
    const members = [i, ...adj[i].slice().sort((a, b) => adj[b].length - adj[a].length).slice(0, 6)];
    if (members.length >= 3) constellations.push({ name: nodes[i].title, members });
  });
  const areas = [...AREA_ORDER, ...new Set(nodes.map(n => n.area).filter(a => !AREA_ORDER.includes(a)))];
  return { vault: app.vault.getName(), areas, nodes, edges, constellations, now: Date.now() };
}

class GalaxyView extends ItemView {
  constructor(leaf, plugin) { super(leaf); this.plugin = plugin; this.frame = null; this.onMessage = e => this.handle(e); }
  getViewType() { return VIEW; }
  getDisplayText() { return 'Neural Brain'; }
  getIcon() { return 'brain'; }
  get page() { return { template: TEMPLATE, prebuilt: PREBUILT, background: '#0e0f12' }; }

  async onOpen() {
    this.addAction('refresh-cw', `Rebuild ${this.getDisplayText()} from your notes`, () => this.loadPage());
    const el = this.contentEl;
    el.empty();
    Object.assign(el.style, { padding: '0', overflow: 'hidden', background: this.page.background });
    this.frame = el.createEl('iframe', { attr: { sandbox: 'allow-scripts', title: this.getDisplayText() } });
    Object.assign(this.frame.style, { width: '100%', height: '100%', border: '0', display: 'block' });
    window.addEventListener('message', this.onMessage);
    // At app start-up the link index may still be filling; wait for it before the first build.
    this.app.workspace.onLayoutReady(() => this.loadPage());
  }

  async loadPage() {
    const adapter = this.app.vault.adapter, { template, prebuilt } = this.page, name = this.getDisplayText();
    try {
      if (await adapter.exists(template)) {
        const tpl = await adapter.read(template);
        const json = JSON.stringify(buildData(this.app, this.plugin.data.opened)).replace(/</g, '\\u003c');
        this.frame.srcdoc = tpl.replace('/*__DATA__*/null', () => json);
      } else if (await adapter.exists(prebuilt)) {
        this.frame.srcdoc = await adapter.read(prebuilt);
        new Notice(`Template not found (${template}); showing the last saved ${name} instead.`);
      } else new Notice(`${name}: template not found (${template}).`);
    } catch (err) {
      console.error(name + ':', err);
      new Notice(`${name} could not be built. See the developer console for details.`);
    }
  }

  // Accept messages only from our own frame, only of the one known shape, and only for notes that exist.
  handle(e) {
    if (!this.frame || e.source !== this.frame.contentWindow) return;
    const d = e.data;
    if (!d || d.type !== 'sb-open' || typeof d.id !== 'string' || d.id.length > 500) return;
    const file = this.app.vault.getAbstractFileByPath(d.id + '.md');
    if (file instanceof TFile) this.app.workspace.getLeaf('tab').openFile(file);
    else new Notice('Note not found: ' + d.id);
  }

  async onClose() { window.removeEventListener('message', this.onMessage); }
}

// ---- flashcards -------------------------------------------------------------------------------------
// A card is one line "question :: answer" in any note under Flashcards/. Its key is deckPath::question,
// so editing the answer keeps the card's schedule; editing the question makes it a new card.
async function loadCards(app) {
  const cards = [];
  for (const f of app.vault.getMarkdownFiles().filter(f => f.path.startsWith('Flashcards/'))) {
    const text = await app.vault.cachedRead(f);
    const body = text.replace(/^---\r?\n[\s\S]*?\r?\n---/, '');
    for (const line of body.split(/\r?\n/)) {
      const m = line.match(/^\s*(?:[-*]\s+)?(.+?)\s+::\s+(.+?)\s*$/);
      if (m) cards.push({ key: `${f.path.replace(/\.md$/, '')}::${m[1]}`, deck: f.basename, file: f, q: m[1], a: m[2] });
    }
  }
  return cards;
}

// SM-2-style scheduling. grade: 0 again, 1 hard, 2 good, 3 easy. Returns the new state.
function schedule(s, grade, today) {
  s = { reps: 0, interval: 0, ease: 2.5, ...(s || {}) };
  if (grade === 0) { s.reps = 0; s.interval = 0; s.ease = Math.max(1.3, s.ease - 0.2); }
  else {
    if (grade === 1) { s.interval = Math.max(1, Math.round(s.interval * 1.2)); s.ease = Math.max(1.3, s.ease - 0.15); }
    else if (s.reps === 0) s.interval = grade === 3 ? 4 : 1;
    else if (s.reps === 1) s.interval = Math.max(s.interval + 1, grade === 3 ? 6 : 3);   // never shorter than last time
    else s.interval = Math.round(s.interval * s.ease * (grade === 3 ? 1.3 : 1));
    if (grade === 3) s.ease += 0.15;
    s.reps++;
  }
  s.due = addDays(today, s.interval);
  return s;
}
const NEW_PER_DAY = 20;

class CardsView extends ItemView {
  constructor(leaf, plugin) { super(leaf); this.plugin = plugin; this.queue = []; this.shown = false; this.deck = ''; this.onKey = e => this.key(e); }
  getViewType() { return CARDS_VIEW; }
  getDisplayText() { return 'Flashcards'; }
  getIcon() { return 'layers'; }

  async onOpen() {
    this.addAction('refresh-cw', 'Reload decks', () => this.start());
    this.containerEl.addEventListener('keydown', this.onKey);
    this.contentEl.tabIndex = 0;
    await this.start();
  }
  async onClose() { this.containerEl.removeEventListener('keydown', this.onKey); }

  async start() {
    const today = localToday(), state = this.plugin.data.cards;
    this.all = await loadCards(this.app);
    const pool = this.all.filter(c => !this.deck || c.deck === this.deck);
    const due = pool.filter(c => state[c.key] && state[c.key].due <= today);
    const fresh = pool.filter(c => !state[c.key]).slice(0, Math.max(0, NEW_PER_DAY - (this.plugin.data.newToday?.[today] || 0)));
    this.queue = [...due, ...fresh];
    this.done = 0; this.shown = false;
    this.render();
  }

  render() {
    const el = this.contentEl;
    el.empty();
    Object.assign(el.style, { display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '28px 20px', gap: '14px' });
    const decks = [...new Set(this.all.map(c => c.deck))].sort();
    const head = el.createDiv({ attr: { style: 'display:flex;gap:10px;align-items:center;width:100%;max-width:640px' } });
    const sel = head.createEl('select', { cls: 'dropdown' });
    sel.createEl('option', { text: `All decks (${this.all.length} cards)`, value: '' });
    for (const d of decks) sel.createEl('option', { text: d, value: d });
    sel.value = this.deck;
    sel.onchange = () => { this.deck = sel.value; this.start(); };
    head.createDiv({ text: `${this.queue.length} to go · ${this.done} done`, attr: { style: 'margin-left:auto;color:var(--text-muted);font-size:12px' } });

    const card = this.queue[0];
    const box = el.createDiv({ attr: { style: 'width:100%;max-width:640px;min-height:220px;padding:24px;border:1px solid var(--background-modifier-border);border-radius:12px;background:var(--background-secondary);display:flex;flex-direction:column;gap:16px' } });
    if (!this.all.length) { box.createDiv({ text: 'No cards yet. Add lines like "question :: answer" to notes in Flashcards/.' }); return; }
    if (!card) {
      box.createEl('h3', { text: this.done ? 'All done for today.' : 'Nothing due today.' });
      const next = Object.values(this.plugin.data.cards).map(s => s.due).filter(Boolean).sort()[0];
      box.createDiv({ text: next ? `Next cards are due ${next}.` : '', attr: { style: 'color:var(--text-muted)' } });
      return;
    }
    box.createDiv({ text: card.deck, attr: { style: 'font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted)' } });
    box.createDiv({ text: card.q, attr: { style: 'font-size:18px;line-height:1.45' } });
    if (this.shown) {
      box.createEl('hr');
      box.createDiv({ text: card.a, attr: { style: 'font-size:16px;line-height:1.5;color:var(--text-accent)' } });
      const row = el.createDiv({ attr: { style: 'display:flex;gap:8px' } });
      ['Again', 'Hard', 'Good', 'Easy'].forEach((label, g) => {
        const b = row.createEl('button', { text: `${label} (${g + 1})` });
        if (g === 2) b.addClass('mod-cta');
        b.onclick = () => this.grade(g);
      });
    } else {
      const b = el.createEl('button', { text: 'Show answer (space)', cls: 'mod-cta' });
      b.onclick = () => { this.shown = true; this.render(); };
    }
    const src = el.createEl('a', { text: 'Open deck note', attr: { style: 'font-size:12px' } });
    src.onclick = () => this.app.workspace.getLeaf('tab').openFile(card.file);
    this.contentEl.focus();
  }

  key(e) {
    if (e.target && (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT')) return;
    if (!this.queue.length) return;
    if (!this.shown && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); this.shown = true; this.render(); }
    else if (this.shown && /^[1-4]$/.test(e.key)) { e.preventDefault(); this.grade(+e.key - 1); }
  }

  grade(g) {
    // Guard against a double click grading the next card unseen: only grade a card whose answer is showing.
    if (!this.shown || !this.queue.length) return;
    const today = localToday(), data = this.plugin.data, card = this.queue.shift();
    if (!data.cards[card.key]) { data.newToday = { [today]: (data.newToday?.[today] || 0) + 1 }; }
    data.cards[card.key] = schedule(data.cards[card.key], g, today);
    if (g === 0) this.queue.push(card);     // see it again before the session ends
    else this.done++;
    this.shown = false;
    this.render();                          // render first, so the old buttons are gone before saving
    return this.plugin.save();
  }
}

// ---- plugin -----------------------------------------------------------------------------------------
module.exports = class SecondBrainGalaxy extends Plugin {
  async onload() {
    this.data = Object.assign({ cards: {}, opened: {}, newToday: {} }, await this.loadData());
    this.registerView(VIEW, leaf => new GalaxyView(leaf, this));
    this.registerView(CARDS_VIEW, leaf => new CardsView(leaf, this));
    this.addCommand({ id: 'open', name: 'Open Neural Brain', callback: () => this.open(VIEW) });
    this.addCommand({ id: 'flashcards', name: 'Review flashcards', callback: () => this.open(CARDS_VIEW) });
    this.addRibbonIcon('brain', 'Open Neural Brain', () => this.open(VIEW));
    this.addRibbonIcon('layers', 'Review flashcards', () => this.open(CARDS_VIEW));
    // Remember when each note is opened (for the galaxy's fading stars). Saved at most every 5 s.
    this.registerEvent(this.app.workspace.on('file-open', f => {
      if (!(f instanceof TFile) || f.extension !== 'md') return;
      this.data.opened[f.path] = Date.now();
      this.dirty = true;
      clearTimeout(this.saveTimer); this.saveTimer = setTimeout(() => this.save(), 5000);
    }));
    this.registerEvent(this.app.workspace.on('quit', () => { if (this.dirty) this.saveData(this.data); }));
    // Keep open-history and flashcard schedules keyed correctly when notes are renamed or deleted.
    this.registerEvent(this.app.vault.on('rename', (f, old) => {
      let changed = false;
      if (this.data.opened[old]) { this.data.opened[f.path] = this.data.opened[old]; delete this.data.opened[old]; changed = true; }
      const from = old.replace(/\.md$/, '') + '::', to = f.path.replace(/\.md$/, '') + '::';
      for (const k of Object.keys(this.data.cards)) {
        if (k.startsWith(from)) { this.data.cards[to + k.slice(from.length)] = this.data.cards[k]; delete this.data.cards[k]; changed = true; }
      }
      if (changed) this.save();
    }));
    this.registerEvent(this.app.vault.on('delete', f => { if (this.data.opened[f.path]) { delete this.data.opened[f.path]; this.save(); } }));
  }

  onunload() {
    clearTimeout(this.saveTimer);
    if (this.dirty) this.saveData(this.data);   // don't lose the last few seconds of open history
  }
  async save() { clearTimeout(this.saveTimer); this.dirty = false; await this.saveData(this.data); }

  async open(type) {
    let leaf = this.app.workspace.getLeavesOfType(type)[0];
    if (leaf) {
      // Obsidian 1.7+ loads background tabs lazily; a deferred leaf has a placeholder view until loaded.
      if (leaf.isDeferred && leaf.loadIfDeferred) await leaf.loadIfDeferred();
      if (leaf.view instanceof GalaxyView) await leaf.view.loadPage();   // already open: rebuild from the latest notes
      else if (leaf.view instanceof CardsView) await leaf.view.start();
    } else {
      leaf = this.app.workspace.getLeaf('tab');
      await leaf.setViewState({ type, active: true });
    }
    this.app.workspace.revealLeaf(leaf);
  }
};
