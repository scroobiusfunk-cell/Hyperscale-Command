# 0001 — CxAlloy is read only: results leave as an export package

**Status:** accepted
**Date:** 2026-09-17
**Supersedes:** the CxAlloy write-back path in `docs/ARCHITECTURE.md`, "Sync and integrations"

## Context

`ARCHITECTURE.md` specifies that on `auto_cleared`, `reviewer_passed`, or
`reviewer_failed` the platform updates the corresponding CxAlloy checklist
line, attaches the evidence photos, and opens an issue for failures. The same
paragraph flags this as conditional: "Confirm the API surface available on the
CxAlloy plan before committing to this path; if write access is limited, a
scheduled export import is the fallback."

Confirmed 2026-09-17: **the CxAlloy API on the current plan is read only.** The
write-back path as written is not available. This is the fallback case the
architecture doc anticipated.

## Decision

1. **Results leave the platform as an export package, not an API write.** A
   completed ruling is rendered into a file that a person imports into CxAlloy.
2. **The read API is used, and used more than originally planned.** The
   equipment list becomes a scheduled API pull rather than a one-off file
   import. The reconciler gets fresher identity data than the original design
   assumed, which is a genuine improvement: the reconciliation queue shrinks
   when CxAlloy changes are picked up automatically instead of at the next
   manual export.
3. **The queue stays.** Retry, ordering, and idempotency machinery are unchanged
   and still tested. Only the terminal action changes, from "POST to CxAlloy" to
   "render into a package and mark delivered".
4. **Delivery is acknowledged explicitly.** A ruling is not "in CxAlloy" because
   we wrote a file. Each exported ruling moves `pending_export` → `exported` →
   `delivery_confirmed`, and only a human confirms the last step.
5. **The client interface is read-only by construction.** `CxAlloyReadClient`
   exposes fetches and nothing else. There is no write method to accidentally
   call, and no stub that silently no-ops a write that a reader of the code
   would assume happened.

## Consequences

### The system-of-record gap is the real cost

CLAUDE.md says: "Nothing in the platform is a system of record. CxAlloy is."
Under write-back that was continuously true — a ruling reached the system of
record seconds after it was made. Under export-import it is true only after a
human does something. Between the ruling and the import, this platform holds
inspection results that the system of record does not know about, and the gap
is measured in days rather than seconds.

That gap cannot be engineered away, so it gets measured instead:

- Every checklist item carries its delivery state, and the reviewer console
  shows the count of rulings not yet in CxAlloy.
- **Undelivered rulings is a tracked metric from day one**, alongside
  reconciliation queue size. Both are leading indicators of the same thing: the
  platform drifting out of step with the physical project.
- Failures alarm sooner than passes. A passed item sitting undelivered is an
  administrative lag; a *failed* item sitting undelivered is a defect nobody has
  been told to fix. The two get different thresholds.

### Evidence photos cannot be attached over the API

The export package is a zip: a manifest file plus the evidence images in a
predictable per-item layout. Whether CxAlloy's importer ingests attachments at
all is unknown — see `docs/OPEN_QUESTIONS.md` Q8. If it does not, the manifest
carries a stable URL into this platform's storage and the photos stay here,
which makes this platform a dependency of the record rather than a feeder to
it. That is worse, and it is worth paying for an upload path to avoid.

### Failure issues become a worklist, not an API call

The platform cannot open a CxAlloy issue. Failed items export as a separate,
smaller file with the observed-versus-expected detail the issue description
would have carried, so the person importing has the least possible work to do.

### Idempotency changes shape

Previously the risk was double-POSTing. Now it is double-importing. Each
exported ruling carries a stable `export_key` derived from the checklist item
and the ruling, and regenerating an export for the same set of rulings produces
the same keys, so a re-import is detectable as duplicate rather than landing
twice. Export generation must be deterministic for this to hold, which means no
timestamps-of-generation inside the compared content.

### Someone acquires a recurring chore

Budget it the way the architecture doc tells us to budget curation: as a real
per-project cost, not an afterthought. Weekly matches the reporting cadence the
project already runs.

### What is unaffected

Phase 1 exit metrics. Reviewer minutes per inspection and the 1,000-labeled-
example target do not depend on how results reach CxAlloy.

## Alternatives considered

**Drive the CxAlloy UI with browser automation.** Rejected. Brittle against any
UI change, probably contrary to the terms of use, and it puts a silent failure
mode directly in the system-of-record path — the one place this project cannot
afford one.

**Make this platform the system of record for inspection results.** Rejected.
It contradicts CLAUDE.md and the liability position in the architecture doc. An
auditor asking who signed off on an item will look in CxAlloy, and the answer
needs to be there.

**Hold the write-back code behind a flag until the plan is upgraded.** Rejected
as the primary plan: it is not a decision we control, and shipping Phase 1
without a working results path is not an option. The read-only interface means
adopting write access later is a swap behind `CxAlloyReadClient` plus a new
delivery backend, not a redesign.
