# Field Inspection Engine

A platform that lets a few qualified inspectors supervise many less-qualified
field techs. It compiles specs and submittals into requirements, binds them to
physical assets, guides a tech through capturing evidence, routes the result to
a remote reviewer, and trains the tech as they go.

It is an inspection assistant and a teaching loop, **not an inspector of
record**. CxAlloy is the system of record.

- `docs/ARCHITECTURE.md` — source of truth for scope, schemas, and boundaries
- `CLAUDE.md` — working rules and current phase
- `docs/OPEN_QUESTIONS.md` — ambiguities found in the doc and the position taken
- `docs/adr/` — decision records

## Current phase

**Phase 1: guided capture.** No computer vision, no auto-clear, no graders.
Everything routes to a human reviewer, and every ruling becomes a labeled
example for Phase 2.

## Layout

```
apps/
  api/          FastAPI backend (Python 3.12, SQLAlchemy 2, Alembic, Pydantic v2)
  field/        React Native + Expo app (TypeScript)
  reviewer/     Next.js reviewer console (TypeScript)
packages/
  schemas/      Shared JSON Schema contracts
infra/          docker-compose for Postgres (pgvector), Redis, MinIO
docs/           Architecture, open questions, decision records
```

## Getting started

Requires Python 3.12, Node 22, and Docker.

```bash
cp .env.example .env
make setup      # API virtualenv and dependencies
make up         # Postgres, Redis, MinIO
make migrate    # apply Alembic migrations
make check      # lint, typecheck, tests
make api        # http://localhost:8000/health
```

Most of the API test suite needs a migrated Postgres and **skips** without one,
so run `make up && make migrate` first. Set `REQUIRE_TEST_DATABASE=1` to turn
that skip into a failure — CI does, so a misconfigured database cannot quietly
delete the safety tests from the run.

`make help` lists the rest. The two TypeScript apps use plain npm:

```bash
cd apps/reviewer && npm install && npm run dev
cd apps/field    && npm install && npm start
```

## Local services

| Service | Address | Notes |
| --- | --- | --- |
| API | http://localhost:8000 | `/health` is the only route so far |
| Postgres | localhost:5432 | `pgvector/pgvector:pg16` |
| Redis | localhost:6379 | Celery broker and result backend |
| MinIO | http://localhost:9000 | Console on :9001, if the pulled release ships one |

MinIO starts with three buckets: `fie-evidence`, `fie-documents`, and
`fie-exports`. They are separate because their lifecycle rules differ —
evidence moves to cold storage after project close, page images stay warm for
curation, and exports are transient.

The MinIO image tags are unpinned on purpose — see the note in
`infra/docker-compose.yml`. Pin `MINIO_IMAGE` and `MC_IMAGE` in `.env` once
you have a release you trust.

## Things worth knowing before you change anything

- **Safety items never clear without a named reviewer.** This is enforced in
  code, and any path that could bypass it is a bug, not a feature request.
- **CxAlloy's API is read only.** Results leave as an export package that a
  person imports. See `docs/adr/0001-cxalloy-read-only-results-export.md`,
  which also covers the failure mode this introduces.
- **All LLM calls go through `app/llm/`.** One module imports the Anthropic SDK
  and nothing else may. A `PromptSpec` pins the prompt, model and version
  together so the eval harness can compare runs by swapping the spec.
- **Schemas in `packages/schemas/` are the contract.** Generate types from
  them; do not hand-write a second copy in an app.
- **No schema edits outside an Alembic migration.** A test asserts that the
  models and the migration agree, so a model changed without one fails CI.
- **Some invariants live in the database.** `safety` requirements cannot reach
  `auto_cleared`, and `ruling` and `labeled_example` reject UPDATE and DELETE.
  These are triggers in the migration, so they hold for the API, a Celery task,
  and a person at a psql prompt alike.
- **The tag reconciler never invents an asset and never guesses an identity.**
  Anything it will not decide goes to the reconciliation queue with its
  candidates and scores attached. Open queue size is a tracked metric: growth
  there means the field is walking to wrong assets.
- Tests are required for the policy layer, precedence resolver, tag reconciler,
  and event replay before those merge.
