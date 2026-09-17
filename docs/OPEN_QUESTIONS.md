# Open Questions

Questions raised while implementing against `docs/ARCHITECTURE.md`. Each entry
records the ambiguity, the option taken in code (the conservative one, per
CLAUDE.md), and what would change if the answer comes back differently.

Status values: `open` (awaiting an answer), `settled` (answered; decision
recorded, code matches), `deferred` (not needed until a later phase).

---

## Q1 — Are the Phase 1 on-device capture gates allowed to use computer vision?

**Status:** open · raised 2026-09-17 · blocks: Capture Plan Compiler, field app

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

**Status:** open · raised 2026-09-17 · blocks: reviewer console, ChecklistItem model

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

## Q6 — CxAlloy API surface is unconfirmed

**Status:** open · raised 2026-09-17 · blocks: write-back queue implementation

`ARCHITECTURE.md` "Sync and integrations" requires confirming the API surface
available on the current CxAlloy plan before committing to write-back, and lists
scheduled export-import as the fallback. This is also an unchecked box in the
doc's own pre-Phase-1 list.

**Position taken:** write-back sits behind a `CxAlloyClient` interface with a
logging no-op implementation. The queue, retry, and idempotency machinery are
real and tested; the transport is stubbed. Nothing in the platform reads from
CxAlloy as a source of truth beyond the initial equipment list import, which is
a file import in Phase 1.

---

## Q7 — Pre-Phase-1 questions from the architecture doc, still unanswered

**Status:** open · raised 2026-09-17 · blocks: nothing yet, but Q7.1–Q7.3 block the pilot

Carried over from `ARCHITECTURE.md` "Open questions to settle before Phase 1".
Recorded here so they have one home.

1. Which equipment class and building for the pilot. *Affects seed data and the first rule set only; code is class-agnostic.*
2. CxAlloy API access level, and write-back versus export-import. *See Q6.*
3. Who curates the first rule set, and how many hours they have. *Curation is the critical path to a usable rule set; no code depends on the answer.*
4. Target false-pass rates per criticality. *Phase 2. Deferred.*
5. Whether the reviewer role sits with the project or a central team. *Affects how reviewers are scoped to projects in the auth model; Phase 1 assumes project-scoped, which is the narrower grant.*
6. Platform ownership: internal tool or product. *No Phase 1 code impact.*

**Also unanswered and needed sooner than expected:** which SSO provider, and
whether it is available in a dev tenant. Safety rulings carry a reviewer's real
identity, so Phase 1 cannot ship on fake logins. Position taken: build against
OIDC with the provider configured per environment, and use a local dev identity
provider that is refused at startup outside development.
