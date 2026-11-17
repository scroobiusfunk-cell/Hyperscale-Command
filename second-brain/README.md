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
Or open the viewer with no `vault.json` and use **Choose your vault folder**: it reads the `.md` files locally in the browser and uploads nothing.
Features: full-text search, area and tag filters, note reader with resolved wikilinks, backlinks, and a graph view.
