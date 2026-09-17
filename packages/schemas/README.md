# @fie/schemas

JSON Schema definitions for the records that cross application boundaries.
These files are the contract between the API, the field app, and the reviewer
console. Per CLAUDE.md, types are **generated** from them — do not hand-write a
duplicate of a schema in any app.

```bash
npm install
npm run validate      # compile every schema, run the examples through them
npm run generate:ts   # emit TypeScript into dist/
```

## Contents

| Schema | Notes |
| --- | --- |
| `requirement.schema.json` | Section 1 of the architecture doc, verbatim field names |
| `asset.schema.json` | Section 2 |
| `checklist-item.schema.json` | Section 2, plus the `blocked_*` and `cxalloy_*` additions |
| `evidence.schema.json` | Designed, not transcribed — the doc gives Evidence no field table |
| `grader-result.schema.json` | Section 4's shared output contract |
| `common/definitions.schema.json` | Shared primitives; not a record |

`GraderResult` is defined in Phase 1 even though nothing produces one, so
`ChecklistItem.grader_result_id` has a real referent and the shared output
contract is fixed before any grader exists to bend it.

`CaptureRecipe` and `LabeledExample` are not here. CLAUDE.md scopes this package
to five schemas, and neither of those crosses an app boundary in Phase 1 — the
field app receives recipe *steps* inside a walk payload, not recipe records.

## Rules encoded here, and what they cost to break

Several constraints exist to make an unsafe record impossible to represent
rather than merely discouraged:

- A `safety` requirement must carry a real `why_it_matters`, not a stub.
- An `approved` requirement must have something to capture, or instantiation
  produces checklist items a tech cannot act on.
- A `blocked` item must record why. Silent deferral is a failure the
  architecture doc names explicitly.
- A `reviewer_passed` or `reviewer_failed` item must name who resolved it and
  when. Nothing clears anonymously.
- `delivery_confirmed` must name the person who confirmed it. The platform
  cannot confirm on a human's behalf that a ruling reached CxAlloy.
- A grader returning `insufficient_evidence` may not also report high
  confidence, and no verdict may cite zero evidence.
- `Evidence` has no verdict field, and `additionalProperties` is false, so one
  cannot be added by accident.

`criticality` is a closed enum on purpose — it drives the safety routing rule,
so an unrecognised value must fail rather than fall through. `equipment_class`
is deliberately *not* closed: the curator extends it per project, and a closed
set would mean a schema change for every new class.

## Validation is the gate, not the TypeScript type

`json-schema-to-typescript` cannot express conditional subschemas, so every
generated type carries an `[k: string]: unknown` index signature and none of the
`if`/`then` rules above survive into TypeScript. A value that typechecks is
**not** necessarily valid.

Validate at the boundary — on API input, on sync, and before export. Do not cast
and hope.

## Changing a schema

- Every field named in `docs/ARCHITECTURE.md` keeps that exact name here, in the
  database, and in the API. If a name looks wrong, raise it; do not rename it.
- Schemas are draft 2020-12 and compile under ajv `strict: true`.
- Add an example to `examples/valid/` for anything newly allowed, and to
  `examples/invalid/` for anything newly forbidden. Invalid examples carry
  `_expect`, a fragment that must appear in the validation error — without it a
  negative test passes for any reason at all, including a typo.
- A schema change that is not backwards compatible needs a matching Alembic
  migration and a note in the PR saying which apps must regenerate types.
