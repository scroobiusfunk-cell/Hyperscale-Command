# 0002 — CxAlloy cannot be written to at all: the export is a worklist for a person

**Status:** accepted
**Date:** 2026-09-18
**Amends:** [ADR-0001](0001-cxalloy-read-only-results-export.md)

## Context

ADR-0001 established that the CxAlloy API is read only and that results would
leave as an export package somebody imports. That last word was an assumption,
and it was wrong.

Confirmed 2026-09-18: **CxAlloy can be updated manually and cannot be automated
at all.** There is no API write, and no bulk import to aim a file at. A person
opens CxAlloy and types the results in.

## Decision

The export package is a **worklist for a human doing repetitive data entry**,
not a file for a machine.

That is not a cosmetic difference. An importer and a person want opposite
things from the same data:

| | An importer wants | A person entering by hand wants |
| --- | --- | --- |
| Shape | One flat normalised table | Rows grouped the way they will work through them |
| Order | Irrelevant | The order they will open equipment in, so each is opened once |
| Progress | Not a concept | Somewhere to keep their place |
| Wording | Column names it can match | Plain language it cannot misread |

So the package leads with `enter_these_in_cxalloy.xlsx`:

- **Results** — one row per ruling, ordered by CxAlloy id, with a `Done` column
  and a frozen header. Failures are shaded.
- **Failures** — the failed items on their own, each carrying `why_it_matters`,
  so whoever raises the issue does not have to go and look it up.
- **How to use** — what this is, and that the platform cannot do it for them.

An asset with no CxAlloy id reads `(not in CxAlloy)` rather than showing blank.
A blank cell looks like an oversight; this is a fact the person needs.

The CSVs stay in the package. They cost nothing, they are what the determinism
and hashing are computed over, and if a machine path ever appears they are
already there.

## Consequences

**The cost of a ruling is now measured in somebody's minutes.** Under ADR-0001
the gap between a ruling and the system of record was a scheduling problem.
Under manual entry it is a labour problem, and it scales linearly with the
number of items the platform clears. That is worth watching: a tool that makes
inspection faster and data entry slower has moved the bottleneck rather than
removed it.

**The undelivered metric matters more, not less.** It is now counting work a
person still has to do, not a file somebody has to move.

**Nothing else changes.** The queue, the retries, the export keys, the delivery
states, the separation of failures from passes and the read-only client are all
unaffected. Only the renderer differs, and it is behind one function.

## Alternatives considered

**Ship the CSVs and let people work from those.** Rejected. A CSV opened in
Excel has no frozen header, no place to tick, and no ordering anybody chose. The
person doing four hundred rows of data entry is the one carrying this
integration, and giving them a raw dump is how the results stop being entered.

**Screen automation against the CxAlloy UI.** Rejected for the same reasons as
in ADR-0001, and now more strongly: "cannot be automated" is a statement about
what is permitted, not only about what is technically possible.
