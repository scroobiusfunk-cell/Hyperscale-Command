# Inspection Understudy AI

Read `docs/ARCHITECTURE.md` before doing anything. It is the source of truth for scope, schemas, and boundaries. If code and the doc disagree, raise it; do not silently pick one.

## What this is

A tool for training green inspectors and superintendents in how to perform an inspection: what to look for, what good looks like, and what wrong looks like. Training is the purpose; the reach it gives a few qualified inspectors is the side effect.

It compiles specs and submittals into requirements, binds them to physical assets, and guides a learner through the walk. At each item the learner sees worked examples, commits to a call before capturing anything, and photographs the evidence. A qualified reviewer rules remotely, and the ruling returns to the learner beside the rule and their own photograph. Agreement between the learner's call and the reviewer's is measured per kind of check.

It is an inspection assistant and a teaching loop, not an inspector of record. The code says *tech* where this says *learner*; they are the same person.

## Current phase

Phase 1: guided capture. No computer vision, no auto-clear. Everything routes to a human reviewer. Do not build graders, calibration, or detectors until Phase 1 exit metrics are met (see the build plan in the architecture doc). If asked for Phase 2+ work, confirm first.

## Non-negotiable rules (enforce in code, not comments)

- Requirements with `criticality = safety` never auto-clear and never self-clear. Any code path that could clear one without a named reviewer is a bug.
- Every grader returns the shared output contract (`verdict`, `confidence`, `evidence_used`, `observed_value`, `expected_value`, `explanation`, versions). `insufficient_evidence` is a first-class verdict.
- Auto-clear thresholds are read from calibration data, never hardcoded constants.
- Reviewer rulings on safety items are append-only. Corrections are new rulings.
- LLM calls go through the provider adapter with prompt, schema, and model version pinned per grader version. No direct SDK calls elsewhere.
- Field app writes are idempotent by client-generated id. Server-side event replay must be safe to run twice.
- Nothing in the platform is a system of record. CxAlloy is. Write-back is a queued, retried side effect.

## Repo layout

```
apps/
  api/          FastAPI backend (Python 3.12, SQLAlchemy 2, Alembic, Pydantic v2)
  field/        React Native + Expo app (TypeScript)
  reviewer/     Next.js reviewer console (TypeScript)
packages/
  schemas/      Shared JSON schemas for Requirement, Asset, ChecklistItem, Evidence, GraderResult
infra/          docker-compose for Postgres (pgvector), Redis, MinIO
docs/           ARCHITECTURE.md and decision records (docs/adr/NNNN-title.md)
```

## Stack decisions already made

Python + FastAPI backend. Postgres with pgvector. S3-compatible object storage (MinIO locally). Celery on Redis for jobs. React Native with Expo for the field app. Next.js for the reviewer console. Company SSO for auth. Do not swap any of these without an ADR in `docs/adr/`.

## Conventions

- Schemas live in `packages/schemas/` as JSON Schema and are the contract between all three apps. Generate types from them; do not hand-write duplicates.
- Every model field named in the architecture doc keeps that exact name in the database and API.
- Tests are required for the policy layer, precedence resolver, tag reconciler, and event replay before any of them merge. These are the places the doc says projects like this die.
- Migrations via Alembic. No schema edits outside a migration.
- Log every external call (LLM, CxAlloy, storage) with a structured record including version and latency.
- Plain language in anything a tech reads. No jargon in `explanation` or `why_it_matters` strings.

## The handover package

An engineer outside this repository is given `scripts/build-handover-package.sh`
output, not a GitHub link: the documents worth reading loose, plus a git bundle
carrying the branch and its history.

**Rebuild it whenever the work changes** — after a commit that touches code,
migrations, `docs/`, or `CLAUDE.md` — and hand over the fresh archive. A
package built from an older head is worse than none, because it looks current.
The script refuses to build from a dirty tree and clone-checks its own bundle
before packaging, so a broken one cannot ship; run it rather than assembling an
archive by hand.

## Working style

- Small, reviewable changes. One subsystem per PR where possible.
- When a requirement in the doc is ambiguous, write the question into `docs/OPEN_QUESTIONS.md` and pick the conservative option (route to human, refuse to clear, surface the conflict).
- Do not invent CxAlloy API behaviour. If the endpoint or field is unknown, stub it behind an interface and note it in `docs/OPEN_QUESTIONS.md`.
- Do not add features beyond the current phase to "save time later".
