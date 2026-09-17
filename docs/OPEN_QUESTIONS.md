# Open Questions

Questions raised while implementing against `docs/ARCHITECTURE.md`. Each entry
records the ambiguity, the option taken in code (the conservative one, per
CLAUDE.md), and what would change if the answer comes back differently.

Status values: `open` (awaiting an answer), `settled` (answered; decision
recorded, code matches), `deferred` (not needed until a later phase).

---

## Q1 — Are the Phase 1 on-device capture gates allowed to use computer vision?

**Status:** settled 2026-09-17 — non-CV gates confirmed · blocks: nothing

`ARCHITECTURE.md` §3 specifies the gate for `visual, presence` as "object
detector confirms class present" and for `visual, readable` as "OCR returns
text above confidence floor". Both are computer vision. `CLAUDE.md` says Phase 1
ships with no computer vision.

**Position taken:** Phase 1 gates use no models. Gates are limited to checks
that measure the capture, never judge its content:

| Recipe | Phase 1 gate | Phase 2 gate (deferred) |
| --- | --- | --- |
| `visual, presence` | Both required shots present; each above a sharpness floor; minimum resolution | Object detector confirms class present |
| `visual, readable` | Framing overlay aligned; label fills the target region of frame; sharpness floor; tech attests the text is legible | OCR returns text above confidence floor |

Sharpness is measured by variance of Laplacian — classical image processing with
no model and no opinion about what is in the photo. Treating that as "computer
vision" would leave Phase 1 with no evidence-quality floor at all.

**Consequence:** with no grader and no CV gate, the reviewer is the only thing
standing between a bad photo and a cleared item. The reviewer therefore needs a
third ruling action alongside pass and fail — see Q5.

**If answered "gates may use CV":** the two gate implementations change; nothing
else does. Recipes are versioned, so this is a new recipe version, not a rewrite.

---

## Q2 — Does "no computer vision" prohibit OCR at document ingest?

**Status:** open · raised 2026-09-17 · blocks: Requirements Compiler ingestion

`ARCHITECTURE.md` §1 step 1 requires "OCR for scanned submittals". Reading a
document is not grading evidence, but it is the same boundary as Q1.

**Position taken:** Phase 1 requires a text layer. Documents without one are
flagged at ingest and surfaced to the curator rather than silently OCR'd or
silently dropped. An `OcrProvider` interface exists with no implementation
registered. Rationale: most spec sections and approved submittals issued in the
last decade carry a text layer, so this may be a cost we never pay on the pilot;
building OCR before we know the pilot's documents need it is work beyond the
phase.

**If the pilot's submittals turn out to be scans:** implement `OcrProvider`
against a dedicated OCR engine, not a vision LLM. OCR output is text for a human
curator to check, so a cheap deterministic engine is the right tool and keeps the
"LLM only in three places" boundary intact.

---

## Q3 — Evidence has no field list in the architecture doc

**Status:** open · raised 2026-09-17 · blocks: schemas, migrations, field app sync

`ARCHITECTURE.md` names Evidence as one of the four core records and references
it throughout, but never gives it a field table the way it does for Requirement,
Asset, ChecklistItem, CaptureRecipe, GraderResult and LabeledExample. It is the
only Phase 1 schema being designed rather than transcribed, so it needs a closer
review than the others.

**Position taken:** the fields below. Two properties are deliberate: Evidence
carries no verdict of any kind (a judgment about evidence lives on
ChecklistItem or GraderResult, never on the evidence itself), and it records
both device and server clocks, because device clocks on a construction site are
not trustworthy.

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Server-assigned |
| client_id | text, unique | Device-generated; the idempotency key for replay |
| checklist_item_id | uuid | |
| capture_recipe_id, capture_recipe_version | uuid, semver | Which recipe and version produced this |
| step_index | int | Which step of the recipe this capture satisfies |
| media_type | enum | `photo`, `video`, `document`, `measurement`. Phase 1 emits `photo` only |
| storage_key | text | Object storage key |
| content_hash | text | sha256; dedupes retried uploads and detects tampering |
| byte_size, mime_type | int, text | |
| captured_at | timestamptz | Device clock |
| received_at | timestamptz | Server clock |
| captured_by | user id | |
| device_metadata | jsonb | Model, OS, app version. Phase 2 needs it to explain grader variance by device |
| gate_results | jsonb | Per gate: id, outcome, measured value. The record of what the gate checked and what it saw |
| retake_of | uuid, nullable | Points at the evidence this replaces, so recapture chains stay visible |
| status | enum | `pending_upload`, `stored`, `superseded`, `rejected` |

---

## Q4 — There is no `deferred` state for checklist items

**Status:** open · raised 2026-09-17 · blocks: ChecklistItem model, Capture Plan Compiler

`ARCHITECTURE.md` §3 says items behind a constraint the tech cannot satisfy are
"deferred with the reason recorded, not skipped silently", but the
`ChecklistItem.state` enum in §2 has no `deferred` value.

**Position taken:** use the existing `blocked` state and add the reason as
separate columns — `blocked_reason` (enum: `no_access`, `energized`,
`not_installed_yet`, `equipment_missing`, `tool_unavailable`, `other`),
`blocked_note` (text) and `blocked_at`. CLAUDE.md requires every field named in
the doc to keep its exact name; adding a value to an enum the doc lists in full
forks the contract for no behavioural gain. `blocked` already means "cannot
proceed", which is what a deferral is, and the reason is the part the doc
actually asks for.

---

## Q5 — The reviewer needs a recapture ruling, not just pass and fail

**Status:** settled 2026-09-17 — recapture action confirmed · blocks: nothing

The policy layer in `ARCHITECTURE.md` §4 routes `insufficient_evidence` to
recapture, but that verdict comes from a grader, and Phase 1 has no graders. The
`ChecklistItem.state` enum offers the reviewer only `reviewer_passed` and
`reviewer_failed`. A reviewer looking at a blurred nameplate has to choose
between failing the installation (wrong — the install may be fine) and passing it
on evidence they cannot read (worse).

**Position taken:** the reviewer gets a third action that returns the item to
`open` with a recapture reason and a note, re-queues it into the tech's walk, and
links the new evidence to the old via `Evidence.retake_of`. No new state value is
added; `open` with recorded history is what a recapture is. Recapture requests
are counted per reviewer and per tech from day one — the rate is the Phase 1
stand-in for the evidence-quality signal that CV gates will provide in Phase 2,
and it tells us which recipes are underspecified.

**Note:** a recapture is not a ruling, so it produces no LabeledExample. Only
pass and fail do.

---

## Q6 — CxAlloy API surface

**Status:** settled 2026-09-17 — API is READ ONLY

The API on the current plan supports reads only. The write-back path in
`ARCHITECTURE.md` is superseded; results leave as an export package and the read
API is used for equipment-list sync. Recorded in
[ADR-0001](adr/0001-cxalloy-read-only-results-export.md), which also covers the
new failure mode this introduces (rulings held in this platform that the system
of record does not yet know about).

Follow-on questions the answer opened: Q8.

---

## Q7 — Pre-Phase-1 questions from the architecture doc, still unanswered

**Status:** open · raised 2026-09-17 · blocks: nothing yet, but Q7.1–Q7.3 block the pilot

Carried over from `ARCHITECTURE.md` "Open questions to settle before Phase 1".
Recorded here so they have one home.

1. Which equipment class and building for the pilot. *Affects seed data and the first rule set only; code is class-agnostic.*
2. ~~CxAlloy API access level, and write-back versus export-import.~~ **Answered: read only, export-import.** See Q6 and ADR-0001.
3. Who curates the first rule set, and how many hours they have. *Curation is the critical path to a usable rule set; no code depends on the answer.*
4. Target false-pass rates per criticality. *Phase 2. Deferred.*
5. Whether the reviewer role sits with the project or a central team. *Affects how reviewers are scoped to projects in the auth model; Phase 1 assumes project-scoped, which is the narrower grant.*
6. Platform ownership: internal tool or product. *No Phase 1 code impact.*

**Also unanswered and needed sooner than expected:** which SSO provider, and
whether it is available in a dev tenant. Safety rulings carry a reviewer's real
identity, so Phase 1 cannot ship on fake logins. Position taken: build against
OIDC with the provider configured per environment, and use a local dev identity
provider that is refused at startup outside development.

---

## Q8 — What does CxAlloy's import accept?

**Status:** open · raised 2026-09-17 · blocks: export package format

ADR-0001 commits to delivering results as an import file, but the importer's
actual capabilities are unknown. Three things decide the export format, and we
are guessing at all three:

1. **File format and columns.** Which file types the importer takes, and which
   columns it matches checklist lines on. Best guess: the column layout of the
   checklist *export*, on the assumption that import mirrors export. Unverified.
2. **Attachments.** Whether photos can be imported at all. If not, evidence
   stays in this platform's storage and the manifest carries URLs into it —
   which makes this platform a dependency of the permanent record rather than a
   feeder to it. ADR-0001 argues that is worth paying to avoid.
3. **Issues.** Whether construction issues can be created by import, or only by
   hand. Decides whether failed items are an import file or a worklist.

**Position taken:** the export renderer sits behind a `ResultsExporter`
interface with one implementation that writes a documented, deterministic CSV
plus a photo directory. The format is expected to change once someone runs a
real import; nothing upstream of the renderer depends on its shape.

**How to settle it cheaply:** hand-build one import file against a test project
in CxAlloy before the exporter is written. An afternoon of someone clicking
through the importer saves rebuilding the format twice.

---

## Q9 — Who imports the export package, and how often?

**Status:** open · raised 2026-09-17 · blocks: nothing in code; blocks the pilot running

ADR-0001 turns results delivery into a recurring manual task. Unowned recurring
tasks do not happen, and the consequence here is not cosmetic: an undelivered
*failed* item is a defect nobody has been told to fix.

**Position taken:** assume weekly, matching the existing reporting cadence, and
build the undelivered-rulings metric so the gap is visible whether or not the
cadence holds. Needs a named owner before the pilot starts.

---

## Q10 — Append-only rulings have nowhere to live

**Status:** settled 2026-09-17 — `Ruling` record approved and implemented

CLAUDE.md: "Reviewer rulings on safety items are append-only. Corrections are
new rulings." `ChecklistItem` cannot satisfy that. It has one `resolved_by` and
one `resolved_at`, both mutable — a correction overwrites the original, which is
exactly what append-only forbids. The architecture doc never defines a Ruling
record, so there is currently nowhere for a ruling's history to go.

This surfaced while drafting the schemas: writing the `reviewer_passed`
constraint made it obvious that the fields it constrains can only ever describe
the *latest* ruling.

Three things need the same missing record:

1. **Corrections.** A superseded ruling has to remain readable, with both
   reviewers named and both timestamps intact.
2. **Recapture requests** (Q5, confirmed). A recapture returns the item to
   `open`, so it leaves no trace on `ChecklistItem` at all. Without a record,
   the count of recapture requests — the Phase 1 evidence-quality signal —
   cannot be computed.
3. **LabeledExample.** Its `human_verdict`, `human_note`, `reviewer_id` and
   `labeled_at` are a projection of a ruling. Deriving them from a mutable
   field means the training data silently changes when a correction is made.

**Resolution:** the proposal below was approved and is implemented in the core
records migration. `ruling` and `labeled_example` are append-only, enforced by a
database trigger rather than by convention.

**Proposal, as built:** a `Ruling` record, append-only, never updated or deleted:
`id`, `checklist_item_id`, `verdict` (`pass` / `fail` / `recapture_requested`),
`note`, `reviewer_id`, `created_at`, `supersedes` (nullable ruling id). The
existing `ChecklistItem.state`, `resolved_at` and `resolved_by` become a
denormalized projection of the newest ruling, kept for query convenience but
never the source of truth. `LabeledExample` is derived from rulings, and a
`recapture_requested` ruling produces none, since it is not a judgment on the
installation.

That adds a sixth schema to `packages/schemas/`, which CLAUDE.md scopes to five,
so it is a question rather than a change already made.

---

## Q11 — Three supporting tables the architecture doc does not describe

**Status:** open · raised 2026-09-17 · already implemented, easy to reverse

The core records could not be given real foreign keys without somewhere for
their references to point, so the core records migration also creates:

| Table | Why | What it would mean to drop it |
| --- | --- | --- |
| `app_user` | `assigned_tech`, `reviewer`, `resolved_by`, `captured_by` and `Ruling.reviewer_id` are all user ids. A ruling that cannot name a real person is precisely what CLAUDE.md forbids | Those columns become unvalidated UUIDs and "named reviewer" stops being enforceable |
| `source_document` | `Requirement.source` is doc id, clause and page. A requirement that cannot point at its clause is not curatable | `source_doc_id` becomes a dangling UUID |
| `project` | Requirements, assets and rule sets are per project; recipes are explicitly shared across projects. Retrofitting tenancy after data exists is expensive | Single-project-only, with a painful migration later |

All three are deliberately thin — SSO owns identity, the Requirements Compiler
will own document content, and `project` holds little more than a name and the
CxAlloy project id.

`project` is the one worth arguing about. It is the only one added for a reason
that is partly about later rather than now, which brushes against the CLAUDE.md
rule about not building ahead of the phase. The counter-argument is that the
architecture doc already assumes multiple projects when it says recipes are
shared across them, and that adding a tenancy column to eight populated tables
later is the kind of change that goes wrong. Say the word and it comes out.

---

## Q12 — Where do project tag prefixes come from?

**Status:** open · raised 2026-09-17 · blocks: nothing; the reconciler works without them

The reconciler can strip leading project or discipline prefixes before
comparing tags, so `DC07-SWBD-101` from a nameplate matches `SWBD-101` in
CxAlloy. It takes that prefix set as a parameter and currently nothing supplies
one, so the default is "strip nothing" — which is the conservative default:
failing to strip a prefix sends an item to the queue, whereas stripping the
wrong thing could match the wrong asset.

**Needs deciding:** whether prefixes are configured per project by the curator,
inferred from the equipment list (the common leading segment across most tags),
or both. Inference is tempting and is exactly the kind of cleverness that
silently merges two buildings' worth of assets, so a configured list reviewed by
a person is the safer starting point.

**Also unsettled:** the three match thresholds (`auto_match` 0.93,
`review_floor` 0.55, `ambiguity_margin` 0.05) are starting values, not measured
ones. They are named constants passed as a parameter rather than inlined, so
tuning them is a visible change. These are *reconciliation* thresholds, not the
auto-clear thresholds CLAUDE.md requires to come from calibration data — nothing
is cleared here, and the cost of a wrong value is queue volume rather than a
wrongly passed inspection. The number to watch once the pilot has real data is
what fraction of queue entries a person resolves by simply agreeing with the
reconciler's top candidate; if that is most of them, the threshold is too tight.
