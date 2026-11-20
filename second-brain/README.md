# Second Brain

An Obsidian-compatible markdown vault plus a small viewer UI. **This repo is public: it contains only code and a synthetic `demo-vault/`. Real vault content (built from Google Drive) lives in Drive / your machine, never here.**

## Vault format (Obsidian-native)
Plain `.md` files with YAML frontmatter (`title, type, area, source, drive_id, modified, tags, summary`), `[[wikilinks]]` (`[[Note]]`, `[[Folder/Note|alias]]`, `[[Note#Heading]]`) and `#tags`. To use in Obsidian: *Open folder as vault* on the vault directory. Nothing else to convert.

## Tools (Node 20+, no dependencies)
```
node tools/check-vault.mjs <vaultDir>               # broken links / missing frontmatter
node tools/build-index.mjs <vaultDir> <out.json>    # index consumed by the viewer
```

## Viewer
```
cd viewer && npm install
VAULT=/path/to/vault npm run build   # indexes the vault and builds ./dist  (default: ../demo-vault)
npm run dev                          # after `npm run index`
```
Single-file version (double-click, works offline, no server): `node tools/make-standalone.mjs viewer/dist viewer/public/vault.json Second-Brain.html` after a build.

Or open the viewer with no `vault.json` and use **Choose your vault folder**: it reads the `.md` files locally in the browser and uploads nothing.
Features: full-text search, area and tag filters, note reader with resolved wikilinks, backlinks, and a graph view.

## Obsidian plugin and Recall (`obsidian/`)
Code that runs inside a vault. Copy `obsidian/tools/*` to `<vault>/_meta/tools/` and `obsidian/plugin/*` to
`<vault>/.obsidian/plugins/second-brain-galaxy/`, then enable **Second Brain** under Community plugins.

- **Neural Brain tab** (ribbon 🧠, "Open Neural Brain"): a rotating 3D robot brain in human shape. Notes are neurons placed
  in lobes by `area`, links are synapses with impulses firing, and a scanner ring sweeps through it. Rendered on a plain 2D
  canvas in a sandboxed iframe (no WebGL, no dependencies); click a neuron to open its note. Also a flashcard review tab
  (SM-2, cards are `question :: answer` lines under `Flashcards/`).
- **Recall** (`node _meta/tools/recall.mjs "<query>" [--n N] [--json] | --links "<note>" | --build`): ranked lookup
  over every note, BM25F over title, aliases, tags, summary, headings and body, with prefix, one-typo and synonym
  fallbacks. The index (`_meta/recall-index.json`) rebuilds itself when any note changes and also writes
  `_meta/Brain Map.md`, one line per note. Synonyms: copy `recall-synonyms.example.json` to `<vault>/_meta/recall-synonyms.json`.
  Point it at another folder with `SECOND_BRAIN_VAULT=<dir>`.
- `node _meta/tools/build-brain-galaxy.mjs`: writes standalone `Second Brain Neural.html` (and the older galaxy page) into the vault.
  Generated HTML and indexes contain your notes: never commit them.
