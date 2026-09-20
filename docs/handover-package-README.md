# Inspection Understudy — handover package

Everything needed to take this project into a corporate repository, in one
archive. Nothing here requires access to the personal GitHub repository it
currently lives on.

Built 2026-09-20. `MANIFEST` records the exact head commit and a checksum for every file.

## Read this first

`docs/HANDOVER.md`. It says what exists, what does not, what must not be
broken, and what is waiting on a decision. Fifteen minutes.

The short version: a working three-application system with 479 passing API
tests and green CI, currently sitting on a branch of a personal repository
whose `main` is an empty commit and whose other branches are an unrelated
Android app. The code is ready to move. The repository is the first problem.

## Importing the code

`inspection-understudy.bundle` is a git bundle: the whole branch, all commits,
in one file. It clones like a remote.

```bash
git clone inspection-understudy.bundle inspection-understudy
cd inspection-understudy
git log --oneline | head            # 34 project commits, newest first
```

That leaves you on the project branch with full history. To push it into a new
corporate repository as `main`:

```bash
git branch -m claude/new-session-1e9687 main
git remote remove origin
git remote add origin git@github.com:<org>/<repo>.git
git push -u origin main
```

**Keep the history if you can.** The commit messages carry the reasoning behind
most of the invariants in `docs/HANDOVER.md`, and several explain why the
obvious simpler implementation is wrong. That is the difference between an
engineer respecting a constraint and deleting it. If policy requires a squashed
import, export the log first:

```bash
git log --format='%h %ad%n%B' --date=short > ../commit-log.txt
```

Verify the bundle before trusting it:

```bash
git bundle verify inspection-understudy.bundle
```

## What is in `docs/`

| File | What it is |
| --- | --- |
| `HANDOVER.md` | Start here. State of the system, what is missing, what to decide |
| `ARCHITECTURE.md` | Source of truth for scope, schemas and boundaries |
| `WORKING-RULES.md` | The project's working rules, including the non-negotiables. Lives in the repository root as `CLAUDE.md` |
| `OPEN_QUESTIONS.md` | 30 questions, each with status, the position taken, and what would settle it |
| `adr/` | Decision records. 0001, CxAlloy read-only, explains a great deal |
| `DEMO.md` | How to demonstrate the system, and the rough edges to know before you do |
| `rule-registry-review-2026-09-20.md` | Review of the Rule Registry design pack, the authoring half of the system. Its finding 10 settles the boundary between the two |

These are copies of files inside the bundle, put here so they can be read and
circulated without cloning anything. The versions in the repository are
canonical.

## Running it, once cloned

```bash
cp .env.example apps/api/.env
docker compose -f infra/docker-compose.yml up -d     # Postgres 16 + pgvector, Redis, MinIO
cd apps/api && pip install -e ".[dev]" && alembic upgrade head && pytest -q
```

`docs/HANDOVER.md` section 6 has the rest, including the exact commands CI runs.

## What is not in this package

- **No credentials of any kind.** No `.env`, no API keys, no CxAlloy secrets.
  `.env.example` inside the repository lists what has to be supplied.
- **No dependencies.** `node_modules` and Python packages install from the
  lockfiles and `pyproject.toml`.
- **No database or object storage contents.** The demonstration data is rebuilt
  by `apps/api/scripts/seed_demo.py`, which goes through the same services the
  applications use.
- **The Rule Registry itself**, which is designed but not built and lives on one
  laptop. Only the review of its design pack is here.
