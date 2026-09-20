> **This document is about the other repository.** The Rule Registry is the
> authoring half of the Field Inspection Engine: rules, failure modes and real
> defect base rates, with importers for CxAlloy, Revit/IFC and scan data. It is
> designed but not yet built, and at the time of writing it existed only on one
> laptop, so a copy lives here to keep the handover self-contained. Its home is
> the Registry repository at `docs/review-2026-09-20.md`; once that repository
> exists, that copy is canonical and this one should go.
>
> Read it for the boundary between the two systems, which is settled in its
> finding 10: the Registry authors, Understudy delivers.

# Review of the task pack, 2026-09-20

Review of `CLAUDE.md`, `AGENTS.md`, `TASKS.md` and `OPEN_QUESTIONS.md` as they stood on
2026-09-20, with the resolutions agreed the same day. Kept because the reasoning behind a
rule is the part that gets lost, and the next person to read `TASKS.md` will want to know
why the invariants are split by owner rather than numbered one to twelve.

Status key: **accepted** as proposed; **accepted with correction** where the reviewer was
wrong on a detail; **open** where nothing is settled yet.

---

## 1. Most invariants were not enforceable where the task put them. Accepted.

`R-02` asked the validator package to enforce all twelve invariants. The validator is a
static checker over record files in this repo, and most of the twelve are not that:

- Static and enforceable here: link resolution, the base rate floor, synthesisable failure
  modes having a perturbation, an approved requirement having an approved check.
- Records that live elsewhere: `SyntheticScene` (split assignment) and `Evidence` /
  `LabeledExample` had no directory in the layout at all.
- Runtime rules: observability yielding `not_visible`, and safety sign-off. Both happen at
  the moment of a ruling, in the delivery app.
- Consumer or process rules: only approved records feeding the generator; a schema version
  bump when a closed enum changes; unmatched issues being reported rather than dropped.
- Half enforceable: a perturbation's `label_effect` listing every affected check "and
  nothing else". The ids can be resolved statically; the exhaustiveness cannot be known
  without running the perturbation.

Told to enforce all twelve in one place, an agent writes checks that pass vacuously, or
stalls on the ones it cannot see.

**Resolution.** Invariants carry stable ids and are grouped by owner in `CLAUDE.md`:
validator, CI, generator, mappers, and the delivery app at runtime. `R-02` enforces the
validator set only, and says so. `GEN_LABEL_EFFECT_EXACT` is a generator-time check;
`INV_LABEL_EFFECT_RESOLVES` is the static half that remains here.

## 2. Eleven against twelve. Accepted.

`TASKS.md` R-02 said "the 11 invariants"; `CLAUDE.md` listed twelve. The twelfth was the
credentials rule, carrying safety sign-off. An agent following the task list literally
builds eleven, and the one it drops is the safety one.

**Resolution.** Counts are gone. Ids only, in code, tests and error messages; numbers are
for humans and may change.

## 3. Read-only CxAlloy enforced by endpoint naming. Accepted with correction.

The original guard refused endpoints whose name ended in `_create`, `_update` or
`_delete`. That catches nothing that matters: a `POST /issue`, an `/addComment`, an
`/issue/save`. A naming convention is documentation, not enforcement.

The reviewer proposed refusing any method other than GET or HEAD. That was wrong, and
`pull/cxalloy.py` is the evidence: TQ serves its paged list endpoints (`/issue`,
`/checklist`, `/test`) over POST, so a method test would have blocked the very reads this
repo exists to make.

**Resolution.** A path allowlist in the transport. `READ_PATHS` in `pull/cxalloy.py`, with
`assert_read_path` raising `ReadOnlyViolation` before signing and before any network call.
`R-05`'s tests assert that an allowlisted POST to `/issue` succeeds against a mock, and
that `/issue_create`, `/addComment`, `/issue/save` and any unlisted path raise first. The
standing rule is now "never add a path to the allowlist that mutates", which is a rule
about a reviewable list rather than about a naming habit.

## 4. The classifier's training labels leaked the label. Accepted.

`R-07b` took its labels from `issue_matching.yaml`, which maps issue *types* to failure
modes, while listing issue type name as a feature. Every issue of a type would carry the
same label, readable from one field. The model would score near-perfectly on held-out data
by learning a lookup table that already exists, and would be useless on exactly the
unmatched issues it was built to place.

**Resolution.** The type mapping is the baseline to beat, not the label. Labels come from a
stratified sample of 300 individually labelled issues, `unmatched` included. Issue type
name is removed from the features. The baseline's accuracy is reported beside the model's
on the same held-out set, and the model ships only if it beats the baseline on the issues
the baseline cannot place.

## 5. Pre-commit on staged files could not check link resolution. Accepted.

`INV_LINKS_RESOLVE` needs the whole store; the targets sit in files that are not staged.

**Resolution.** Pre-commit runs the validator over the whole repo, and `CLAUDE.md` says why.

## 6. A missing input would cascade rather than stop. Accepted.

Sections 9 and 10 of `docs/architecture.md` are the input to `R-03`, and `R-04`, `R-06` and
`R-07` all stand on `R-03`. Combined with the standing rule "write why in
`OPEN_QUESTIONS.md` and move on", one missing input produced a repo of half-built stages
rather than one clear stop. (The sections were in the repo; the reviewer had only the four
files that were uploaded.)

**Resolution.** A dependency rule at the top of `TASKS.md`, and `BLOCKS:` lines on the tasks
that carry one. A blocked task with a `BLOCKS` line stops the run.

## 7. `equipment_types.yaml` was circular between R-06 and R-07. Accepted.

`R-06` created the lookup with every `equipment_class` null and had to pass validation;
`R-07`'s human step filled the nulls.

**Resolution.** The yaml is a project lookup, not a schema record, so null is permitted
there. An Asset whose type resolves to null is written with `equipment_class: unresolved`
and counted in the report, so `R-06` passes before `R-07`.

## 8. Ambiguities. All accepted.

- **Thirty rows, how many requirements?** Now stated: 30 Requirements and 30 Checks, one to
  one for this batch, merged by hand later if they come to share a check.
- **Versioning of approved records.** An edit makes a new record with a new id, plus
  `supersedes` and `record_version`. `index.json` exposes one `current` per chain, and
  `INV_SINGLE_CURRENT_VERSION` guarantees at most one approved record in a chain.
- **The 0.85 threshold, recomputed to what?** Now a criterion: per class, the lowest
  threshold at which held-out precision reaches 0.95; if no value does, that class is never
  auto-matched. Coverage is reported per class.
- **Commit authorship before SSO exists.** A signed dev header is allowed in `R-08` and is
  marked in the commit trailer as `Auth: dev-header`. No unmarked dev writes.

## 9. Drift risks. Accepted.

- `AGENTS.md` and `CLAUDE.md` were byte-identical with nothing keeping them so. `AGENTS.md`
  is now a generated copy, and `CI_AGENTS_MIRROR` fails the build if they differ.
- Two build orders existed, and the shorter one in `CLAUDE.md` was missing credentials and
  the classifier. `TASKS.md` is now the only build order.
- Invariant numbers lived in prose while error messages cited them. Ids now, per finding 2.

## 10. The boundary with Inspection Understudy. Accepted, and now `R-00`.

The Registry and Understudy had both built requirement authoring: a `draft` to
`needs_review` to `approved` to `retired` state machine, curation endpoints, and in
Understudy a precedence resolver for conflicting documents. Separately, one idea carried
four vocabularies: `pass | fail | indeterminate | not_visible` here, against Understudy's
`insufficient_evidence` for graders, `recapture_requested` for rulings, and `unsure` for
the learner's own call.

**Resolution.** Registry authors; Understudy delivers. Authoring moves here. Understudy
keeps the extraction step of its requirements compiler, writes `draft` Requirement records
here, and reads `index.json`. Verdicts unify on `pass | fail | indeterminate |
not_visible`, with the old distinctions surviving as a `reason` field on `indeterminate`.
`R-11` gives Understudy a pure library, `registry.authority`, so tier and safety decisions
are computed in the app at ruling time and the Registry never sits in the synchronous path
of a ruling.

---

## Still open

- **Where the shared verdict definition physically lives.** `R-00`'s definition of done
  names a shared `verdicts.py` imported by both repos, but nothing says which repo owns it
  or how the other one gets it. Understudy already treats JSON Schema in `packages/schemas`
  as its cross-app contract, with parity tests on both the Python and the TypeScript side,
  so the neutral home may be a schema that both repos check against rather than a Python
  module that one of them imports. Unsettled.
- **`R-00` needs a package that `R-01` creates.** `R-00` is first in the work order and its
  done-when requires an importable module; `R-01` is the scaffold that would contain that
  module, and is marked `BLOCKS: everything`. However it is resolved, the two tasks
  disagree about which comes first.

## Not faults, worth keeping

`MAP_CLASSIFIER_PROPOSES`, the classifier proposing matches while only confirmed ones count
toward rates, is the rule most projects skip. `INV_BASE_RATE_FLOOR`, refusing to show a rate
below five confirmed issues rather than showing a bad one, is the same discipline as a
first-class `indeterminate` verdict: saying "not enough to tell" instead of guessing.
"Present them as a single review table, not as questions" will save hours of round trips.
