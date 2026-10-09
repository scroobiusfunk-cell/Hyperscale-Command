# CDR Campus QA/QC & Commissioning Training (Cx Path)

Mobile-first PWA that trains new hires, field engineers and QA/QC & Cx admins on the QTS CDR Campus (DC4, DC5, DC7) QA/QC and commissioning process (Suffolk L1–L5 Flowchart R5, QTS CX Standard V1.4 (S7117) Rev 39).

Role track → 7 core modules (overview, hard rules, role duties, lesson steps, check) → 15-question final check (80% / 12 of 15) → electronic acknowledgment → CSV completion record. Also: practice games, equipment checklist lookup, hard-rule cheat card, glossary, admin team readiness (sample data).

## Run

```
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + production build (service worker included)
npm run preview
npm test
```

Debug flags: `?unlock=1` opens every module and the final check; `?notes=0` hides lesson field notes.

## Structure

- `src/content/content.json` — source of truth for all copy and data (from the design handoff). Spec revisions are a content edit.
- `src/lib/logic.ts` — unlock rules, pass mark, scoring, CSV, filters (unit-tested in `tests/`).
- `src/state/store.ts` — progress persisted to `localStorage` key `cxpath-v2` (track, completed modules, best score, acknowledgment).
- `src/screens/`, `src/components/` — UI. `src/styles/industry.css` is the Industry design-system stylesheet.
- PWA: `vite-plugin-pwa` precaches the app, content and images, so it works offline.

## Open decisions (not built; see design handoff)

1. Delivery (native vs. mobile web vs. embedded in Red Blue University).
2. SSO and role-based gating — the admin view currently follows the self-selected track.
3. LMS push (SCORM/xAPI/API) — currently CSV export only.
4. Final-check retake policy (currently unlimited, best score kept).
5. Whether trade modules (EL/ME/CT) become required.
6. Server-side records and offline progress sync (progress is local to the device).
7. Technical sign-off of content by the Campus Sr Cx Manager; verify "QA/QC Plan §12.4" (cited from the deck only).
8. Confirm licensing of `src/assets/tiltwatch-tripped.png` (likely a manufacturer photo).

The handoff's `source-docs/` (project-confidential specs and decks) are deliberately not committed.
