# Handover

For the engineer taking this into a corporate repository. It says what exists,
what does not, what must not be broken, and what you have to decide.

Written 2026-09-20 against commit `0869cfa`.

---

## 1. What this is

**Inspection Understudy** trains green inspectors and superintendents to perform
an MEP commissioning inspection: what to look for, what good looks like, what
wrong looks like. It compiles specifications and submittals into requirements,
binds them to physical assets, and walks a learner through the inspection. At
each item the learner sees worked examples, **commits to a call before
capturing anything**, then photographs the evidence. A qualified reviewer rules
remotely, and the ruling returns to the learner beside the rule and their own
photograph. Agreement between the learner's call and the reviewer's is measured
per kind of check.

That last sentence is the product. Everything else is plumbing for it. It is an
inspection assistant and a teaching loop, not an inspector of record: CxAlloy
remains the system of record and this platform never claims to be.

There is a second, related design in flight, the **Rule Registry**: a
git-backed store of inspection rules, failure modes and real defect base rates,
with importers for CxAlloy, Revit/IFC and laser scan data. It is designed but
not built. The boundary between the two is settled and written down: the
Registry authors rules, Understudy delivers them. See section 9.

## 2. Before anything else: the repository situation

This is the first thing to fix and it is not a code problem.

The work currently lives on a **branch of a personal repository that is mostly
something else**:

| | |
| --- | --- |
| Repository | `scroobiusfunk-cell/Hyperscale-Command`, private, personal account |
| `main` | a single empty initial commit |
| `claude/new-session-1e9687` | **all 32 commits of this project** |
| `claude/smart-home-device-manager-fyiom2` | an unrelated Android smart-home app |
| `apk-latest` | a built APK from that Android app |

The repository name refers to the Android app, not to this.

**Recommendation.** Create a new corporate repository, import
`claude/new-session-1e9687` as its `main`, and leave the Android branches
behind. Keeping history is worth it: the commit messages carry the reasoning for
most of the decisions in section 5, and several of them explain why an obvious
simpler implementation is wrong. If your corporate policy requires a squashed
import, export the log first.

CI is a single workflow, `.github/workflows/ci.yml`, with four jobs and no
third-party actions beyond `actions/checkout`, `actions/setup-python` and
`actions/setup-node`. It needs a Postgres service container and nothing else.
It is green on the current head.

## 3. What is built

Three applications and one shared contract, in a monorepo.

| Path | What | Size |
| --- | --- | --- |
| `apps/api` | FastAPI backend, Python 3.12 | ~10,000 lines, 36 test files |
| `apps/field` | React Native / Expo field app | ~4,100 lines |
| `apps/reviewer` | Next.js reviewer console | ~4,500 lines |
| `packages/schemas` | JSON Schema, the cross-app contract | 6 schemas |
| `apps/api/alembic` | 11 migrations | |

Working, end to end, verified by driving the real applications rather than only
by unit test:

- **Requirements compiler.** PDF ingestion, clause-aware section splitting,
  LLM extraction behind a provider adapter, grouping requirements that govern
  the same check, precedence resolution across conflicting documents, conflict
  surfacing, rule-set versioning and a curation workflow.
- **Checklist instantiation and the policy layer.** Requirements bind to assets;
  the policy layer decides what routes to a human. In Phase 1 everything does.
- **Walk compiler.** Groups items by asset, sequences by location, defers items
  behind an access constraint with the reason recorded.
- **Offline capture.** An outbox on the device: nothing leaves until the server
  acknowledges it and nothing is deleted until then. Idempotent replay keyed by
  a client-generated id, safe to run twice.
- **Predict-then-reveal.** The learner commits to a call before the camera. The
  server refuses a call on an item that already carries a ruling, which is the
  guard the whole agreement metric rests on.
- **Reviewer console.** Queue with safety first, one-action ruling with a
  mandatory note on anything that is not a pass, append-only corrections.
- **The teaching loop.** The ruling returns to the learner beside their own
  photograph, with agreement computed per kind of check.
- **Worked examples.** Captioned right and wrong examples per kind of check,
  downloaded with the walk so they are on the phone in a basement.
- **CxAlloy delivery.** Build an export package, download it, confirm by hand.
  Read-only throughout; see section 5.

**What proves it:** 479 API tests against a real migrated Postgres, 59 field
tests, ruff, ruff format, mypy strict, three TypeScript typechecks, JSON Schema
validation with worked valid and invalid examples, and a migration round trip
(`upgrade head` to `downgrade base` to `upgrade head`) in CI.

`docs/DEMO.md` is a runbook for a 10-minute demonstration on seeded data, and
`apps/api/scripts/seed_demo.py` builds that data through the same services the
applications use, so the seeded state is state the system could have reached.

## 4. What is not built

Stated plainly, because a handover that oversells is worse than useless.

- **No computer vision, no graders, no auto-clear.** Phase 1 routes every item
  to a person. The grader output contract and the policy layer exist so that a
  Phase 2 grader has something to satisfy, and the evidence and rulings being
  collected are what it would be measured against.
- **No calibration and no thresholds.** Deliberate: auto-clear thresholds must
  come from calibration data, never from a constant in the code.
- **The requirements compiler has never run on a real specification.** It has
  been tested against documents written for the purpose. This is the single
  highest-value next experiment: one piece of equipment, its spec sections, its
  approved submittal, its drawings, and its existing CxAlloy checklist, then a
  three-way comparison of what the compiler found, what the checklist has, and
  what each missed.
- **No SSO.** Auth is a development header, gated behind
  `AUTH_DEV_IDENTITY_ENABLED` and refused outside `ENVIRONMENT=development`.
  Company OIDC is the intended replacement and the seam is there.
- **No live CxAlloy connection.** A read-only client exists in the Rule Registry
  pack with HMAC signing and a path allowlist, and is not yet wired into this
  repository. Nothing here has ever called CxAlloy.
- **No per-project authorisation.** See section 8. This is the one gap that
  should block a second project.
- **The Rule Registry is not built at all**, only designed.

## 5. The rules that must not be broken

These are enforced in the database and in tests rather than in review comments,
because every one of them is a thing that would otherwise be quietly undone by a
refactor. If you change a subsystem, these are what to re-check.

**In the database.** Four triggers and twenty-two check constraints, including:

- `trg_checklist_item_no_safety_auto_clear` — a `criticality = safety`
  requirement can never reach `auto_cleared`. Criticality lives on the
  requirement, not the item, so this cannot be a check constraint; a trigger is
  the only way to enforce it in the schema.
- `trg_ruling_append_only`, `trg_labeled_example_append_only`,
  `trg_prediction_append_only` — rulings, their labelled examples and a
  learner's call are never updated or deleted. A correction is a new ruling
  pointing at the one it supersedes; both stay readable.
- `ck_*_reason_iff_indeterminate` — a verdict of `indeterminate` must say which
  kind it is, and a definite verdict must not claim otherwise.
- `ck_requirement_safety_has_real_reason` — a safety requirement cannot carry a
  stub `why_it_matters`.
- `ck_*_by_a_person` (five of them) — a resolved, approved, published or
  delivery-confirmed record names the human who did it.

**In code and convention.**

- **CxAlloy is read-only.** Results leave as an export package a person enters
  by hand. ADR-0001 records the decision; the Delivery page and the export
  queue exist because of it.
- **LLM calls go through one provider adapter**, with prompt, schema and model
  version pinned per grader version. There are no direct SDK calls anywhere
  else, and the Rule Registry's rule scopes this further: runtime
  classification, matching and routing are in-house; a hosted model is for
  document extraction at authoring time only.
- **Schemas in `packages/schemas` are the contract.** Generate types from them.
  Two parity tests, one Python and one TypeScript, fail the build when an app's
  copy of a shared enum drifts. They exist because a copy had already drifted
  in silence.
- **Nothing is a system of record.** CxAlloy is.
- **Tests are required** for the policy layer, the precedence resolver, the tag
  reconciler and event replay before any of them merge.

## 6. Running it

```bash
cp .env.example apps/api/.env
docker compose -f infra/docker-compose.yml up -d     # Postgres 16 + pgvector, Redis, MinIO
cd apps/api && pip install -e ".[dev]" && alembic upgrade head
uvicorn app.main:app --port 8000
cd ../reviewer && npm ci && npm run build && npm run start
```

Tests, exactly as CI runs them:

```bash
cd apps/api      && ruff check . && ruff format --check . && mypy app tests && pytest -q
cd apps/field    && npm ci && npm run typecheck && npm test
cd apps/reviewer && npm ci && npm run lint && npm run typecheck && npm run build
cd packages/schemas && npm ci && npm run validate && npm run generate:ts
```

`REQUIRE_TEST_DATABASE=1` turns a missing Postgres into a failure rather than a
silent skip. The database-level guards above need a real Postgres, so do not
let anyone swap in SQLite for speed.

For the demonstration, `docs/DEMO.md`.

## 7. What the corporate environment has to provide

| Need | Why | Notes |
| --- | --- | --- |
| Postgres 16 with `pgvector` | Primary store; the extension is for spec retrieval | Nothing in Phase 1 uses vectors yet; the extension is created in a migration |
| S3-compatible object storage | Evidence photographs, reference images, export packages, source documents | MinIO locally; four buckets |
| Redis | Celery broker for queued work | Scaffolded, lightly used in Phase 1 |
| Anthropic API key | Document extraction in the requirements compiler only | Authoring-time. No customer photograph is sent to any model in Phase 1 |
| CxAlloy read-only key | Pull of issues, checklists, equipment | Not yet wired here. The key already exists |
| OIDC / company SSO | Replaces the development header | Reviewer identity is on every ruling, so this matters before a pilot |

Runtime surface is small: FastAPI, SQLAlchemy, Alembic, Pydantic, psycopg,
Celery, boto3, structlog, the Anthropic SDK, pypdfium2 for PDF rendering and
openpyxl for the CxAlloy worklist. Front ends are Next.js and Expo with no
exotic dependencies. All permissive licences; worth a pass through your own
tooling regardless.

## 8. Data and security posture

**What leaves the building.** Document text goes to Anthropic during
requirements extraction, through the provider adapter, and every such call is
logged with its model version and latency. Nothing else goes anywhere. In
particular no evidence photograph is sent to any model in Phase 1, because
there is no grader.

**Evidence.** Photographs live in object storage, served through the API rather
than by signed URL so that looking at one needs the same identity as ruling on
it. A reviewer or admin may see any evidence; anyone else sees only what they
captured.

**The gap you should care about.** There is no project membership anywhere in
the schema. `AppUser` carries global roles, so a reviewer's reach is every
project in the deployment. That is tolerable for a single-project pilot and is
not tolerable for the second. Closing it needs a membership table, which is a
real modelling decision rather than something to bolt onto an authorisation
helper. Recorded as Q28.

**Audit.** Every ruling names its reviewer and is append-only. Every external
call, LLM, storage and CxAlloy, is logged structurally with version and latency.

## 9. Decisions waiting on you

1. **Where the Rule Registry lives, and whether it is built.** The design pack
   is complete and reviewed; the review is in this repository as
   `docs/rule-registry-review-2026-09-20.md`, because the Registry repository
   does not exist anywhere shared yet.
   Until it exists, the second half of its task R-00 is blocked: rule authoring
   is meant to move there and Understudy is meant to read its `index.json`. The
   authoring code here works in the meantime, so nothing is stuck, but two
   implementations of requirement authoring should not both survive.
2. **`verdict_reason` may need a fourth value.** The Registry's architecture
   defines a measurement inside the instrument's noise band as `indeterminate`.
   That is a fourth kind, and the enum has three. Cheap now, a schema version
   bump across two repositories later. Q30.
3. **Per-project authorisation.** Q28, above. Before project two.
4. **Whether the shared contract stays JSON Schema.** R-00 asked for a shared
   Python module; it was built as `$defs` in `packages/schemas` instead, because
   a module is importable by one repository and copied into the other. If the
   Registry disagrees, settle it before either side holds real data.
5. **Phase gate.** Do not build graders, calibration or detectors until the
   Phase 1 exit metrics in `docs/ARCHITECTURE.md` are met. The temptation will
   be strong and the metrics exist to resist it.

## 10. Where to look

| File | What it is |
| --- | --- |
| `docs/ARCHITECTURE.md` | Source of truth for scope, schemas and boundaries |
| `CLAUDE.md` | The working rules, including the non-negotiables in section 5 |
| `docs/OPEN_QUESTIONS.md` | 30 questions, each with status, position taken and what would settle it |
| `docs/adr/` | Decision records. 0001 is CxAlloy read-only, and explains a lot |
| `docs/DEMO.md` | How to demonstrate it, and the rough edges to know first |
| `docs/rule-registry-review-2026-09-20.md` | Review of the Rule Registry design pack, with each finding's resolution. Its finding 10 settles the boundary between the two systems |
| `apps/api/alembic/README.md` | The Postgres enum traps this schema has already hit |

Read `docs/OPEN_QUESTIONS.md` before changing anything structural. It is not a
backlog; it is the record of what was deliberately left undecided and why, and
most arguments you are about to have with the code are already in there.
