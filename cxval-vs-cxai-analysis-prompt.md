# Prompt: Cx-Val vs CX-AI Commissioning Matrix — full comparative analysis

> Paste everything below the line into Claude in VS Code, in the workspace that has the Cx-Val
> repo open. Both subjects of the analysis are in the repo: Cx-Val's own source, and the
> competitor's demo unpacked under `research/cx-ai-demo/`.

---

I need a rigorous functional comparison between **Cx-Val** (ours, in this repo) and a competing
product, **CX-AI Commissioning Matrix** / "Matrix AI". Both target the same end goal — telling a
commissioning team what is ready for turnover — by different routes. If one wins the category I
intend it to be ours, which means this analysis has to survive a hostile reviewer: no claim that
the evidence does not support, and an explicit list of where the competitor is genuinely ahead.

You have everything you need locally. Do not fetch anything.

## The two bodies of evidence

**Cx-Val** — this repository. The source is the arbiter of what Cx-Val does.

**CX-AI** — `research/cx-ai-demo/`. Read its `README.md` first. Their product demo, unpacked:
58 pre-rendered pages of the real application under `pages/`, the route and API surface in
`manifest.json` and `assets/api.json`, their stylesheet, and the demo's own packaging shim. This
is their actual shipped HTML, so it is strong evidence of their real functionality.

## Ground rules

1. **Do the CX-AI teardown yourself.** Form your own conclusions from `research/cx-ai-demo/`
   before you look at Appendix Z. I have done a prior read; it is sealed at the end of this prompt
   precisely so it does not anchor you.
2. **Verify every Cx-Val claim against the source.** Cite `file.ext:line`. If a capability exists
   only in docs, comments, roadmap or a TODO, label it `CLAIMED — NOT IN CODE`.
3. **Ignore the demo's data.** Their sample content is fabricated for sales. Volumes, completion
   rates and gaps in sample data are irrelevant. Judge capability only.
4. **Demo ≠ product.** Tag every CX-AI conclusion `OBSERVED` (in their files), `IMPLIED` (from
   route/API/config surface), or `UNKNOWN`. Never state they lack something you merely did not see.
5. **Do not flatter.** Where they lead, say so and rank it by what it costs us in a bake-off.
6. Read-only analysis. Do not refactor anything. Note defects separately.

---

# Part A — Tear down CX-AI

Work through `research/cx-ai-demo/` and build their functional inventory from scratch. Method that
works on this material:

- `manifest.json` gives every route. The route list alone tells you how the product is organised.
- `assets/api.json` gives their API endpoints and shapes.
- The matrix pages (`matrix__*.html`) are the main screen: read the header row, the per-row data
  attributes, the cell markup, and the inline `<script>` blocks — the filtering and sorting logic
  is in there in full.
- `checklist-*.html` shows their inspection form structure; `issues-*.html` their defect model;
  `executive_summary__*.html` their metric set; `config__*.html` their configuration model;
  `document_viewer__*.html`, `schedule__*.html`, `integrations__*.html` the remaining surfaces.
- `assets/app.css` and the page markup show what UI affordances exist even where the demo stubs
  the data behind them.

Establish at minimum, with evidence:

1. **Their state model.** The exact status vocabulary in the cell markup, what drives each value,
   and — the question that matters most — **what a status actually asserts**. Is it progress?
   Lateness? Verified completion? Something else? Quote the markup.
2. **Their workflow model.** The stage columns, how many, what they are, and whether a project can
   define its own.
3. **Their asset model.** How an asset is identified, what attributes it carries, how it groups
   (family, type, system, building, floor, space), and whether anything maps an asset across
   external systems.
4. **Their filter, search, sort and roll-up surface.** Everything a user can slice by.
5. **Their inspection form.** What a checklist captures: line items, results, evidence, signatures.
6. **Their defect model.** Issue fields, statuses, assignment, linkage back to checklist lines.
7. **Their configuration model.** What an administrator can change per project — in particular
   their template and link-template tooling.
8. **Their document handling.** What the document viewer does and what it is wired to.
9. **Their reporting and schedule surfaces.** What exists, and what is placeholder.
10. **Their integration surface.** What their API and routes imply about data sources, and whether
    anything suggests ingestion from a system of record.

Also answer: **what question is their product built to answer?** Their state vocabulary, their
summary tiles and their column model are the evidence. Be precise, because Part C turns on it.

---

# Part B — Establish what Cx-Val does, from the code

For each item: does it exist, where (`file:line`), and is it shipped / partial / planned?

1. **Ingestion** — the CxAlloy API integration: endpoints, auth and key handling, pull scope
   (asset / checklist / line / file), batching, caching, rate-limit handling, scheduling, retry,
   audit logging. Is the pull reconciled against source anywhere in code or tests?
2. **Master asset register** — how asset identity is modelled and mapped across systems; how many
   assets are actually mapped in data or fixtures; how tag collisions are resolved.
3. **The readiness engine** — locate the rule implementation. Confirm in code: Not started /
   Complete / Review / Open defect; the "100% passed but never closed" rule; permitted vs
   impermissible N/A; missing required file, photo or signature; a failed line whose linked issue
   is closed but which was never re-answered. Quote the exact predicate for each.
4. **Requirements matrix** — how per-asset photo and report requirements are sourced and applied,
   and whether inferred rows are distinguished from confirmed ones in code.
5. **Roll-ups** — worst-state propagation and line-weighted percentage across asset → skid →
   system → building, and whether drill-down exists.
6. **Multi-project normalisation** — how differently configured CxAlloy projects are reconciled.
7. **Reporting** — daily and weekly report generation: what exists, what is templated, what is
   manual.
8. **Security posture** — read-only enforcement, secret storage, access control, retention.
9. **Testing** — any regression suite over the readiness rules. This matters disproportionately:
   rules nobody can change safely are not a product.
10. **Scale** — record volumes handled in code and fixtures, and any performance work.

Then reconcile against these **claims from our own roadmap deck** — claims to verify, not truth:
4,791+ assets mapped across DC4–DC7; a live read-only CxAlloy API pull verified against source;
the four-state engine coded and verified; the daily report cut from ~2 hours to minutes on
CDR1-DC4; an L2M closeout control gap found from v1 data; Phase 1 remaining = attachment flags at
checklist and line level, line-level integrity by asset/skid/checklist type, confirmation of
inferred requirements-matrix rows; open product decisions = the Orange split (In progress vs
Review), photo size floor and tag vocabulary, attribute acceptance ranges, person-to-company map.
**Flag every claim the code does not support.**

---

# Part C — The analysis

## C1. Feature parity matrix
One row per capability. Columns: Capability | CX-AI (state + OBSERVED/IMPLIED/UNKNOWN + file) |
Cx-Val (state + `file:line`) | Winner | Delta size (None / Cosmetic / Material / Category-defining)
| Notes. Group by: ingestion and data foundation, status semantics, asset model, workflow and
stages, UI and navigation, filtering and search, inspection forms, defects and blockers, documents
and attachments, configuration, reporting, schedule and forecasting, security and governance,
testing and reliability.

## C2. The thesis, tested — do not assume it
My contention is that the two products answer **different questions**: theirs reports *progress
against a date*, ours asserts *whether a completion is real*. If that holds, a tracker will
faithfully report a checklist that is lying, and that is the category-defining difference.

Test it against both bodies of evidence and tell me honestly whether it holds, partially holds, or
overstates. Specifically: does anything in their system verify evidence rather than record
answers? Does their Corrective Action column, their issue categories, or anything in their
configuration model already do part of this work? If the thesis is weaker than I think, say so
plainly — I would rather find out here than in front of a client.

## C3. Deltas, quantified
For each material difference: what it is, which product leads, the size of the gap in plain terms,
what it would cost *them* to copy us, what it would cost *us* to copy them, and how defensible the
lead is. Address directly whether the asset register, requirements matrix and encoded client Cx
standard are genuinely the expensive, defensible parts — or whether their configuration tooling
gets them there another way.

## C4. Interchangeability
- Which of their patterns could we adopt directly, and what would it take?
- Could their inspection form be a capture layer over our verification engine — are the two
  complementary rather than competing?
- Data-model correspondence: their stage columns ↔ our readiness states; their configuration and
  link templates ↔ our requirements matrix; their asset grouping ↔ our master asset register.
  Give the mapping table, and say where the mapping breaks.
- If we ever had to ingest their system as a source, what would that take?

## C5. Where they are ahead, and how we close it
Ranked. For each: the gap, why it wins demos, the cheapest credible answer from our side, and
effort. This is the section that makes the rest believable.

## C6. The case for Cx-Val
Only after the above, and only on what you evidenced: what Cx-Val delivers that CX-AI has not been
shown to, why our route is the harder and more defensible one, and the risk of doing nothing. No
adjectives doing work that evidence should do.

## C7. Evidence appendix
Every Cx-Val assertion with `file:line`. Every CX-AI assertion with its file and tag. A list of
everything you could not verify.

---

# Output

Write to `docs/analysis/cxval-vs-cxai.md`. Lead with a one-page executive summary: the thesis as
it survived testing, the three deltas that decide the category, the three gaps we must close.

Do not commit or push unless I ask. Report in chat: the three findings that most change my
position, every roadmap claim the code did not support, and every point where your independent
read of CX-AI disagreed with Appendix Z.

---

# Appendix Z — prior read of CX-AI (open only after Part A)

A previous analysis of the same files, for cross-checking. **Where we disagree, your reading of
the files wins** — say so and show the evidence.

- Route surface: `/projects`, `/select_project/<id>`, `/?project_id=<id>&initial_limit=N`,
  `/executive_summary`, `/config`, `/schedule`, `/integrations`, `/document_viewer`,
  `/issues/<n>`, `/issues/unassigned`, `/checklist/<n>`.
- API: `/api/get_remote_search`, `/api/pdfs`, `/api/pdf_categories` (Mechanical, Electrical,
  Plumbing, Fire Protection, Low Voltage, Other), `/api/matrix_signature`.
- Six stage columns: Pre-Installation, Installation, Pre-Functional Checklist, Start-Up & TAB,
  Functional Testing, Corrective Action.
- Cell status vocabulary: `complete`, `in_progress`, `overdue`, `warning`. Row badges:
  `BEHIND SCHEDULE`, `WARNING: DUE SOON`, `% Complete`, `STAGE FINALIZED`. Read as
  schedule-driven: progress and lateness, with no evidence-verification dimension.
- Filters: building, division, contractor, family, type, floor, space, priority, plus text search.
  Sorts: Default, Most Complete, Most Incomplete, Most Overdue, Most Due Soon, Most In Progress.
  Plus master progress bars, collapsible groups, a dates toggle, export and drawing modals.
- Checklist form: nameplate and submittal data; pre-start verification with initials; witnessed
  test results Pass/Fail/N/A; a team sign-off table.
- Issues: open count per asset; status (Open, In Dispute), priority, category (Installation
  Deficiency, Documentation Gap), assignee, due date, modified, systems, description; an
  unassigned bucket.
- Executive summary tiles: Assets, Checklists, Complete, In Progress, Due Soon, Overdue,
  Corrective Actions, Schedule Position.
- Configuration tabs: Project Assets, Stages / DataLinks, Priority List, View Settings, Template
  Generator, Link Templates. Equipment grouped family → type → unit with CSI MasterFormat codes.
  **Assessed as a real strength — a user-configurable stage and template model.**
- `/schedule` and `/integrations` render "This view is ready for layout and data wiring" —
  placeholder in their own demo.
- Not seen anywhere: attachment or evidence verification as a gating rule; detection of a
  checklist at 100% that was never closed; detection of a failed line whose issue is already
  closed; N/A permission rules; cross-system asset identity; ingestion from a system of record;
  forecasting; automated report generation. All `UNKNOWN`, not absent.
