# @fie/schemas

JSON Schema definitions for the records that cross application boundaries.
These files are the contract between the API, the field app, and the reviewer
console. Per CLAUDE.md, types are **generated** from them — do not hand-write a
duplicate of a schema in any app.

## Rules

- Every field named in `docs/ARCHITECTURE.md` keeps that exact name here, in the
  database, and in the API. If a name looks wrong, raise it; do not rename it.
- Schemas are draft 2020-12 and compile under `--strict=true`.
- A schema change that is not backwards compatible needs a matching Alembic
  migration and a note in the PR description saying which apps must be
  regenerated.

## Consumers

| Consumer | How it uses these |
| --- | --- |
| `apps/api` | Pydantic models are the source of the API surface; these schemas are checked against them in tests |
| `apps/field` | `npm run generate:ts` produces TypeScript types |
| `apps/reviewer` | `npm run generate:ts` produces TypeScript types |

## Contents

Schemas land here in the next change. Planned set, per CLAUDE.md:
`Requirement`, `Asset`, `ChecklistItem`, `Evidence`, `GraderResult`.

`GraderResult` is defined in Phase 1 even though nothing produces one, so that
`ChecklistItem.grader_result_id` has a real referent and the shared output
contract is fixed before any grader exists to bend it.
