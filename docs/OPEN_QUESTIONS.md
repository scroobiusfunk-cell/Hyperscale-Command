# Open Questions

Questions raised while implementing against `docs/ARCHITECTURE.md`. Each entry
records the ambiguity, the option taken in code (the conservative one, per
CLAUDE.md), and what would change if the answer comes back differently.

Status values: `open` (awaiting an answer), `settled` (answered; decision
recorded, code matches), `deferred` (not needed until a later phase).

---

## Q1 — Are the Phase 1 on-device capture gates allowed to use computer vision?

**Status:** settled 2026-09-17 — non-CV gates confirmed, and built into the two recipes

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

---

## Q13 — Where does a referenced standard sit in the precedence order?

**Status:** open · raised 2026-09-17 · blocks: nothing; the resolver surfaces these

`ARCHITECTURE.md` gives the order as contract documents over approved submittal
over manufacturer IOM, with approved deviations and RFI responses as the two
exceptions. It lists `standard` as a document type but never says where a
referenced standard ranks against the others.

**Position taken:** a standard is ranked last, but a standard that disagrees with
a higher-ranked document is surfaced as a conflict rather than silently losing.
The reasoning is that a standard is usually incorporated *by* the contract rather
than competing with it, so "loses quietly" is the wrong default: if the spec and
the standard it cites disagree, somebody needs to know.

**Cost if this is wrong:** curation load. Every spec-versus-standard disagreement
lands in front of a person. If that turns out to be constant noise on a real
document set, the fix is to rank standards properly rather than to stop
surfacing them.

---

## Q14 — Safety conflicts are always surfaced, which raises curation cost

**Status:** open · raised 2026-09-17 · implemented, worth challenging

The precedence resolver refuses to resolve *any* group of competing requirements
where at least one is `criticality: safety`, even when the document hierarchy
gives a clear answer. A qualified person picks.

This is a judgment call, not something the architecture doc states. The argument
for it: the doc already requires every safety requirement to be human-approved
before it goes live, so these conflicts reach a person regardless; having the
resolver pick a winner first would only mean the person reviews a decision
already made, which is how a rubber stamp starts.

The argument against: it inflates the curation queue on a document set with many
safety requirements, and curation time is the cost the doc tells us to budget
honestly. If the pilot shows this is the bulk of the queue, the narrower rule is
to surface only where the *losing* candidate is safety.

Worth revisiting once there is a real spec section to measure against.

---

## Q15 — Requirement identity is (id, ruleset_version), not id alone

**Status:** settled by the doc 2026-09-17 · implemented

`ARCHITECTURE.md` describes `Requirement.id` as "stable across versions where the
requirement is unchanged". The core records migration took `id` as the primary
key on its own, which quietly contradicts that: a spec revision produces a new
rule set carrying the same requirement, and two rows cannot share a primary key.
Left alone, every revision would have minted new ids and the version diff the doc
asks for — "a new version and a diff, not a silent overwrite" — would have had
nothing stable to diff against.

**Implemented:** the primary key is `(id, ruleset_version)`. `ChecklistItem`
already records both, so its foreign key is composite, which also gives the
useful property that an item points at one requirement *as it was in the rule set
that generated the item*. `LabeledExample.requirement_id` keeps no foreign key —
its checklist item already guarantees integrity — and is documented as a
denormalized copy.

This is the doc being implemented rather than a deviation from it, but it changed
a shipped migration's shape, so it is recorded here.

**One real deviation alongside it:** `Requirement` gains `approved_by` and
`approved_at`, which the doc's field table does not list. A safety requirement
that went live with nobody's name on it cannot be defended later, and
`RuleSet.published_by` only records who published the set, not who approved each
requirement in it. A check constraint enforces that an approved requirement names
its approver.

---

## Q16 — Document ingestion

**Status:** settled 2026-09-17 — built

Everything downstream of ingestion exists — extraction, precedence, curation,
versioning — but nothing yet turns a PDF into the section text and page images
those steps consume. `SourceDocument` has a `storage_key` and no reader.

**What it needs, per `ARCHITECTURE.md` section 1:** PDF to text plus layout
(headings, tables, clause numbers), the page image stored alongside so every
requirement can show its source, and the text-layer check from Q2 that flags a
scanned document to the curator rather than silently OCR'ing or dropping it.

**Built with pypdfium2** (permissively licensed, extracts text and renders page
images from one library). Page text lives in Postgres because the splitter and
extraction read it constantly; page images live in object storage because they
are large and only read when someone opens a clause. Re-uploading the same file
is a no-op, keyed on a sha256 of the bytes, because a spec gets re-sent whenever
somebody is unsure it landed.

The text-layer check from Q2 is implemented: `present`, `partial` or `missing`.
A scanned document is stored and flagged rather than rejected — the page images
are still worth having and a person needs to see that the file arrived — and the
compiler refuses to run on it with a reason rather than producing nothing.

---

## Q17 — When do two requirements govern the same check?

**Status:** settled 2026-09-17 — option 1 built, option 2 available as an override

The precedence resolver takes a *group* of competing requirements and ranks
them. It does not decide what a group is, and that turns out to be the harder
half of the problem. Compilation currently sets each requirement's
`precedence_rank` from its document type's base rank and never groups anything,
so conflicts between a spec and a submittal are not being detected yet.

Grouping needs a rule for "these two requirements check the same thing on the
same equipment". Candidates, roughly in order of how much they can go wrong:

1. **Exact match on `applies_to` plus `pass_criteria`.** Cheap, deterministic,
   and will miss almost every real conflict, because two documents describing
   the same check word it differently.
2. **`applies_to` plus a curator-assigned check key.** A person tags equivalent
   requirements. Accurate and slow, and it adds to the curation cost the
   architecture doc already tells us to budget honestly.
3. **Model-proposed grouping, human-confirmed.** The model suggests "these two
   are the same check"; the curator confirms. Fits the platform's existing shape
   — the model proposes, a person decides — but it is a second model call per
   requirement pair and needs its own prompt version and eval.

**Built: option 1, with option 2 as the escape hatch.** Extraction now asks the
model for a `check_subject` — a short noun phrase naming the thing being checked,
with no values or qualifiers, so two documents describing the same check produce
the same phrase. That plus the equipment class, system and location type
normalizes into a `check_key`, and requirements sharing a key go through
precedence resolution together. A curator can edit `check_key` to group the pairs
the rule missed, which is option 2 without any extra machinery.

The normalization is deliberately literal: case and punctuation are ignored
(so "name plate" groups with "nameplate"), and nothing else is. No synonyms, no
stemming. "arc flash label" and "arc flash warning label" will not group, and
that is the intended direction to fail in — a missed group is two checklist
items, which a tech notices and a reviewer clears, while a wrong group silently
discards one document's requirement and nobody finds out until the rework.

A missing system or location type is treated as a literal wildcard rather than a
match-anything, so a requirement that applies everywhere does not quietly absorb
one scoped to electrical rooms.

**Option 3 was not built.** Model-proposed grouping needs its own prompt version,
its own eval and a second call per pair, and none of that is worth doing before
there is a real document set to measure the deterministic rule against. The
number to watch on the pilot is how many conflicts a curator creates by hand
with a `check_key` edit; if that is most of them, the rule is too literal.

**Consequences elsewhere:** a rule set with an open conflict cannot be published.
Two documents disagreeing about a check is exactly the thing that should not
reach a tech, and resolving a conflict is a person picking the winner, which
retires the losers rather than deleting them — which document lost and who
decided is the answer when someone later asks why the submittal's version is not
being checked.

---

## Q18 — What is an "item type"?

**Status:** open · raised 2026-09-17 · blocks: nothing in Phase 1; blocks calibration in Phase 2

Calibration, golden sets, competency scores and the spot-check audit are all
computed *per item type*, and `ARCHITECTURE.md` never says what one is. The
policy layer takes it as a string and nothing computes it yet, which is harmless
while nothing is calibrated and a landmine the day something is.

The choice decides how much data each threshold is computed from, and the
architecture doc says an item type needs roughly 200 reviewed examples before it
counts as calibrated. Too fine a grain and nothing ever reaches 200; too coarse
and one threshold covers checks with genuinely different error rates.

Candidates:

1. **Per requirement.** Finest grain, most defensible statistically per item,
   and almost nothing will reach 200 examples on a single project.
2. **Per (verification method, capture recipe).** e.g. `visual_presence`,
   `visual_readable`. Coarse enough to accumulate data quickly; lumps "is there
   a label" together with "is there a firestop collar", which fail differently.
3. **Per (equipment class, check subject).** Uses the `check_key` machinery Q17
   already added. Middle grain, and it is the grouping a reviewer would
   recognise as "the same kind of check".

**Leaning towards 3**, reusing `check_key` without the system and location
parts, but this should be decided against real labelled data rather than in the
abstract — the honest answer is whichever grain reaches 200 examples while
keeping the observed false-pass rates within a type similar to each other.

Nothing is blocked meanwhile: `NoCalibration` has no answer for any item type,
so every item routes to a reviewer regardless of what the string says.

---

## Q19 — Walk sequencing is by room, not by route

**Status:** open · raised 2026-09-17 · blocks: nothing; costs the tech walking time

The Capture Plan Compiler sequences stops by room, then grid reference, then
tag. That is stable and followable, and it is not a route: it does not know
which rooms are next to each other, which way the corridors run, or that the
riser is quicker than the stairs.

Real sequencing needs floor geometry, which nothing in the platform has. The
model coordinates on `Asset` are optional and stay empty until scan integration
in Phase 4.

**Position taken:** room order, and say plainly that it is not optimised. A
wrong route costs a tech minutes of walking; a clever route built on data nobody
has would cost them trust in the whole walk.

**Worth measuring on the pilot:** whether techs reorder the walk themselves. If
they consistently do, the fix is probably to let them, rather than to guess
better.

---

## Q20 — Access constraints are extracted, and nobody has checked them

**Status:** open · raised 2026-09-17 · blocks: nothing yet; worth a look during curation

`Requirement.access_constraints` is new, and the extraction model populates it:
whether a check needs the equipment dead, a ladder, or a confined space permit.
The capture plan defers items whose constraints the tech's declared state does
not satisfy, so a wrong value has real consequences in both directions — a
missing `requires_deenergized` sends someone to open a live board, and a spurious
one defers work that could have been done.

The doc's own list of constraints ("which rooms are open, what is energized,
whether a ladder is available") implies this field has to exist, but the field
table does not include it, so this is an addition.

**Needs deciding:** whether the curation screen should surface
`access_constraints` as something a curator explicitly confirms rather than
something they have to notice. Given what a missed `requires_deenergized` costs,
the answer is probably yes for any requirement the model marks safety.

---

## Q21 — How do the photo bytes get to the server?

**Status:** open · raised 2026-09-18 · blocks: the field app's upload path

Sync carries the event log, and a `capture_taken` event names a `storage_key`,
a `content_hash` and a byte size. It does not carry the photo. Something has to
put the bytes at that key, and nothing does yet.

The options differ mostly in what happens on a bad connection, which is the only
connection this app will ever have:

1. **Presigned upload URLs.** The server hands the app a key and a presigned PUT
   per capture; the app uploads directly to object storage and syncs the event
   afterwards. Resumable, no photo bytes through the API, and it needs the
   storage endpoint reachable from the phone.
2. **Multipart upload through the API.** Simpler to reason about and to
   authorise, and it puts a 3 MB photo through the API for every capture on a
   site with one bar of signal.

**Leaning towards 1**, with the event synced only after the bytes land, so an
event never references a key with nothing behind it.

**Either way there is an ordering problem worth deciding explicitly:** today
nothing checks that the object exists when the event is applied. Evidence rows
can therefore point at keys that were never uploaded — a walk that synced from
the car park before the photos finished. The conservative fix is a verification
pass that marks such evidence `pending_upload` rather than `stored`, which is
what that enum value is for and why it exists unused.

---

## Q22 — A walk has no server-side identity

**Status:** open · raised 2026-09-18 · blocks: nothing; limits what can be measured

Sync events carry a `client_walk_id` the device generates, and there is no
`walk` table. Events group by it and that is all it does.

That is enough for Phase 1 — the event log replays correctly and the checklist
items carry the state — but it means the platform cannot say how long a walk
took, which items were downloaded versus attempted, or whether a tech finished
one. "Inspections per tech per day" is on the day-one metrics list in the
architecture doc and cannot be computed from this.

**Position taken:** no walk table yet, because inventing its fields before the
field app exists would be guessing at what the app actually knows. The
`walk_completed` event carries `items_attempted`, which is the start of an
answer.

**Worth revisiting** as soon as the field app is real enough to say what a walk
means to it.
