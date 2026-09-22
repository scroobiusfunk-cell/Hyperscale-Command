# Prompt: Cx-Val vs CX-AI Commissioning Matrix — full comparative analysis

> Paste everything below the line into Claude in VS Code, in the workspace that has the Cx-Val
> repo open. It is self-contained: the competitor findings are included because that agent
> cannot reach the competitor demo.

---

You have the Cx-Val codebase in this workspace. I need a rigorous functional comparison between
Cx-Val and a competing product, **CX-AI Commissioning Matrix** ("Matrix AI"), whose interactive
demo I have already had fully decompiled. The competitor findings are given below as fact — you
do not need to fetch anything. Your job is to establish **what Cx-Val actually does in code**,
compare the two, and produce the deliverable described at the end.

## Why this matters

Both products target the same end goal — telling a commissioning team what is ready for turnover
— by different routes. If one wins the category I intend it to be Cx-Val. I need an analysis that
survives a hostile reviewer: no marketing claims that the code does not support, and an explicit
list of where the competitor is genuinely ahead, each with a closing move.

## Ground rules (these are not optional)

1. **Verify every Cx-Val claim against the source.** Cite `file.ext:line` for each capability you
   assert. If a capability exists only in docs, comments, roadmap or a TODO, label it
   `CLAIMED — NOT IN CODE`. A reviewer will check.
2. **Do not flatter.** Where CX-AI does something Cx-Val does not, say so plainly and rank it by
   how much it would cost us in a bake-off.
3. **Separate the demo from the product.** The competitor evidence is a *static demo snapshot* of
   their app. Absence of a feature in the demo is evidence about the demo, not proof their product
   lacks it. Mark every competitor inference as `OBSERVED` (in demo artifacts), `IMPLIED`
   (from their route/API surface), or `UNKNOWN`. Never claim they lack something you only failed
   to see.
4. **Distinguish shipped / partial / planned for Cx-Val** using the code as arbiter, not the deck.
5. Read-only analysis. Do not refactor, do not "fix" anything you find. Note defects separately.

---

# Part A — Competitor evidence: CX-AI Commissioning Matrix (verified)

Source: their published demo artifact, a single ~9.0 MB HTML file. Everything here was read
directly out of it.

## A1. How the demo is built (tells you about their real app)

- One HTML shell containing a JSON blob of **58 server-rendered pages**, keyed by their real app
  routes. An iframe is fed each page via `srcdoc`; a hash-based router (`__cxRoute`) swaps pages.
- An injected shim intercepts clicks, form submits, `fetch` and `window.open` so nothing escapes
  the demo. Writes are disabled: *"This demo is read-only - saving is disabled."*
- **Their real route surface, leaked by the demo** (strong evidence of the actual product):
  `/projects`, `/select_project/<id>`, `/?project_id=<id>&initial_limit=N`, `/executive_summary`,
  `/config`, `/schedule`, `/integrations`, `/document_viewer`, `/issues/<n>`, `/issues/unassigned`,
  `/checklist/<n>`.
- **Their API surface, stubbed in the demo**: `/api/get_remote_search`, `/api/pdfs`,
  `/api/pdf_categories` (returns `Mechanical, Electrical, Plumbing, Fire Protection, Low Voltage,
  Other`), `/api/matrix_signature`.
- Signals of a server-rendered app (inline `onclick`, global `applyFilter()`, form POSTs, no SPA
  bundle), ~36 KB hand-written CSS, base64 logo, brand navy `#00205B`. Treat stack inference as
  `IMPLIED`.

## A2. Scope of the demo

Three projects (data hall, airport terminal, medical pavilion), each with its own configuration,
asset inventory and stage set — so **per-project configuration and project switching are real
capabilities**, not hardcoding. Ignore the demo's data volumes and any gaps in its sample content:
they are artifacts of a sales demo and tell you nothing about the product. Judge capability only.

## A3. Their functional inventory (OBSERVED unless marked)

**Matrix (main screen)** — assets as rows against **6 stage columns**: Pre-Installation,
Installation, Pre-Functional Checklist, Start-Up & TAB, Functional Testing, Corrective Action.
- Cell states, from `data-status`: `complete`, `in_progress`, `overdue`, `warning`.
  **Their state model is schedule-driven** — the four states encode progress and lateness, and
  nothing else. This is the single most important functional fact in this document.
- Row badges: `BEHIND SCHEDULE`, `WARNING: DUE SOON`, `% Complete`, `STAGE FINALIZED`.
- Row attributes carried for filtering: building, division, family, type, floor, space, priority,
  issue count, asset name, asset type.
- Filters: building, division, contractor, asset family, asset type, floor, space, priority
  (multi-select dropdown), plus free-text asset search.
- Sorts: Default, Most Complete, Most Incomplete, Most Overdue, Most Due Soon, Most In Progress.
- UI: master progress bars (complete / in-progress / overdue / warning), collapsible headers and
  asset groups, a show-dates toggle, an export modal, a drawing-page modal, a global loading
  overlay, and animated page transitions.

**Checklist detail** — a real commissioning form: nameplate & submittal data (make, model, serial,
system tag, nameplate voltage); pre-start verification items with status and initials; witnessed
test results with Pass / Fail / N/A per step; a team sign-off table (installing contractor,
controls, etc.) with name/signature/date.

**Issues** — per asset, with open issue count; each issue has status (`Open`, `In Dispute`),
priority, category (`Installation Deficiency`, `Documentation Gap`), assignee, due date, modified
date, affected systems, description. An `/issues/unassigned` bucket exists.

**Executive summary** — filter bar (priority, contractor, division, building, asset family, asset
type, floor, space) over KPI tiles: Assets, Checklists, Complete, In Progress, Due Soon, Overdue,
Corrective Actions, and a **Schedule Position** indicator ("On Schedule").

**Project configuration** — tabs: Project Assets, Stages / DataLinks, Priority List, View Settings,
**Template Generator**, **Link Templates**. Equipment inventory is grouped family → type → unit
with CSI MasterFormat codes (e.g. `23 07 00` air handling, `23 64 00` chillers, `23 81 00` CRAH).
This is a configurable stage model and template system — treat it as a real strength.

**Document viewer** — PDF upload with category assignment, drag-and-drop, "Open a processed
drawing or reference document", a `/api/pdfs` listing and a "Refresh". In the demo the endpoint
returns empty. Their PDF handling is `IMPLIED` to be real in-product.

**Not built even in their demo**: `/schedule` and `/integrations` both render
*"This view is ready for layout and data wiring."* — placeholder text. Their schedule and
integrations stories are `UNKNOWN` at best, and their own demo declines to show them.

## A4. What their evidence does NOT show

No sign, anywhere in the demo, of: attachment/file-presence verification as a gating rule;
detection of a checklist at 100% that was never closed; detection of a failed line whose linked
issue is already closed; N/A permission rules; cross-system asset identity resolution; API
ingestion from a system of record; forecasting; or automated report generation. Mark all of these
`UNKNOWN`, not absent. What you *can* say is that none of it appears in the functional surface
they chose to expose — routes, API endpoints, state vocabulary, configuration tabs — and that
surface is a reasonable proxy for what the product is organised around.

---

# Part B — What to establish about Cx-Val, from the code

Work through the repo and produce an evidenced inventory. For each item: does it exist, where, and
is it shipped / partial / planned?

1. **Ingestion** — the CxAlloy API integration: endpoints called, auth and key handling, pull
   scope (asset / checklist / line / file), batching, caching, rate-limit handling, scheduling,
   retry, audit logging. Is the pull reconciled against source anywhere in code or tests?
2. **Master asset register** — how asset identity is modelled and mapped across systems; how many
   assets are actually mapped in data or fixtures; how tag collisions are resolved.
3. **The four-state readiness engine** — locate the rule implementation. Confirm in code:
   Not started / Complete / Review / Open defect; the "100% but still open" rule; permitted vs
   impermissible N/A; missing required file / photo / signature; failed line whose issue is closed.
   Extract the exact predicate for each and quote it.
4. **Requirements matrix** — how per-asset photo/report requirements are sourced and applied, and
   whether inferred vs confirmed rows are distinguished in code.
5. **Roll-ups** — worst-colour propagation and line-weighted percentage across asset → skid →
   system → building. Is drill-down implemented?
6. **Multi-project normalisation** — how differently configured CxAlloy projects are reconciled.
7. **Reporting** — daily/weekly report generation: what exists, what is templated, what is manual.
8. **Security posture** — read-only enforcement, secret storage, access control, retention.
9. **Testing** — any regression suite over the readiness rules. This matters disproportionately.
10. **Scale** — actual record volumes handled in code/fixtures, and any performance work.

Reconcile what you find against these **claims made in our own roadmap deck** (treat as claims to
verify, not truth): 4,791+ assets mapped across DC4–DC7; live read-only CxAlloy API pull verified
against source; four-state engine coded and verified; daily report cut from ~2 hours to minutes on
CDR1-DC4; an L2M closeout control gap found from v1 data; Phase 1 remaining items = attachment
flags at checklist and line level, line-level integrity by asset/skid/checklist type, confirming
inferred requirements-matrix rows; open product decisions = Orange split (In progress vs Review),
photo size floor and tag vocabulary, attribute acceptance ranges, person-to-company map.
**Flag every claim the code does not support.**

---

# Part C — The analysis I want

## C1. Feature parity matrix
Every capability as a row. Columns: Capability | CX-AI (state + OBSERVED/IMPLIED/UNKNOWN) |
Cx-Val (state + `file:line`) | Winner | Delta size (None / Cosmetic / Material / Category-defining)
| Notes. Group by: ingestion & data foundation, status semantics, asset model, UI & navigation,
filtering & search, detail views, issues & blockers, documents & attachments, configuration,
reporting, schedule & forecasting, security & governance, testing & reliability.

## C2. The central thesis, tested
My contention is that the two products answer **different questions**, and that ours is the one
that matters:
- CX-AI's cell states (`complete`, `in_progress`, `overdue`, `warning`) and its "Schedule Position"
  tile answer **"is this asset late?"** — a progress tracker with a date overlay.
- Cx-Val's four states answer **"is this asset's completion real?"** — it catches 100%-but-open,
  impermissible N/A, missing required files, and failed lines closed by an issue that never
  re-answered the line.
A progress tracker faithfully reports a checklist that is lying. Test this thesis against both
bodies of evidence and tell me honestly whether it holds, partially holds, or overstates. If their
`Corrective Action` column or `Documentation Gap` issue category already does some of this work,
say so.

## C3. Deltas, quantified
For each material difference, state: what it is, which product leads, the size of the gap in
plain terms, what it would cost *them* to copy us, what it would cost *us* to copy them, and how
defensible the lead is. Be specific about the moat: the asset register, the requirements matrix and
the encoded client Cx standard are the expensive parts — verify that claim against the code and
say how replicable they are.

## C4. Interchangeability
Where the two could be swapped, borrowed from, or joined:
- Which of their UI patterns could we adopt directly (stage-column matrix, filter/sort surface,
  Template Generator, Link Templates, priority model, per-issue detail pages, document category
  model)?
- Could their per-asset checklist form be a front end over our engine — i.e. are they a capture
  layer and we a verification layer?
- Is there a data-model correspondence (their stage columns ↔ our readiness states; their
  DataLinks ↔ our master asset register; their requirements-by-template ↔ our campus requirements
  matrix)? Give the mapping table.
- If we ever had to ingest *their* system as a source, what would that take?

## C5. Where they are ahead, and how we close it
Ranked. For each: the gap, why it wins demos, the cheapest credible answer from our side, and
effort. Be blunt — this is the section that makes the rest believable. Candidates to assess
honestly: a user-configurable stage model with template generation and link templates (they let a
project define its own commissioning workflow — can we?), document/drawing viewing tied to assets,
per-issue detail pages with assignment and dispute status, the breadth of their filter/sort
surface, and per-project configuration as a first-class feature.

## C6. The case for Cx-Val
Only after the above. Written so a sceptical executive can check every line: what Cx-Val delivers
that CX-AI has not been shown to, why the route we took is the harder and more defensible one, and
what the risk is if we do nothing. No adjectives doing work that evidence should do.

## C7. Evidence appendix
Every Cx-Val assertion with its `file:line`. Every competitor assertion tagged. A list of anything
you could not verify.

---

# Output

Write to `docs/analysis/cxval-vs-cxai.md` in this repo (create the path). Lead with a one-page
executive summary: the thesis, the three deltas that decide the category, and the three gaps we
must close. Then the full analysis.

Do not commit or push unless I ask. When you are done, tell me in chat: the three findings that
most change my position, and every roadmap claim the code did not support.
