# Field Inspection Engine

Read `docs/ARCHITECTURE.md` before doing anything. It is the source of truth for scope, schemas, and boundaries. If code and the doc disagree, raise it; do not silently pick one.

## What this is

A platform that lets a few qualified inspectors supervise many less-qualified field techs. It compiles specs and submittals into requirements, binds them to physical assets, guides the tech through capturing evidence, grades what it can, routes the rest to a remote reviewer, and trains the tech as they go. It is an inspection assistant and a teaching loop, not an inspector of record.

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

## Working style

- Small, reviewable changes. One subsystem per PR where possible.
- When a requirement in the doc is ambiguous, write the question into `docs/OPEN_QUESTIONS.md` and pick the conservative option (route to human, refuse to clear, surface the conflict).
- Do not invent CxAlloy API behaviour. If the endpoint or field is unknown, stub it behind an interface and note it in `docs/OPEN_QUESTIONS.md`.
- Do not add features beyond the current phase to "save time later".
