# Running the demonstration

A script for showing Inspection Understudy AI to somebody who has not seen it.
It assumes nothing is running.

The point to land is in the third act. The first two — a walk compiled from
specification, a reviewer ruling from anywhere — are things other tools do. The
third, a learner's judgement measured against a qualified person's, per kind of
check, is the one nobody has built, and it is the reason the rest exists.

---

## Before anybody arrives

Five things run: Postgres, object storage, the API, the reviewer console, and
the seed. Locally that is `infra/docker-compose.yml` plus two dev servers.

```bash
# 0. Settings. The API reads apps/api/.env; the defaults in .env.example match
#    the compose stack, so a straight copy works.
cp .env.example apps/api/.env

# 1. Postgres, Redis and MinIO (this also creates the buckets)
docker compose -f infra/docker-compose.yml up -d

# 2. A clean database beside the development one
cd apps/api
export PGPASSWORD=understudy_local_dev
createdb -h localhost -U understudy understudy_demo
export DATABASE_URL=postgresql+psycopg://understudy:understudy_local_dev@localhost:5432/understudy_demo
alembic upgrade head

# 3. The demonstration project
python scripts/seed_demo.py
```

The seed prints the ids everything else needs. Put the project id and Ray
Okafor's id in `apps/reviewer/.env.local`:

```
UNDERSTUDY_API_URL=http://127.0.0.1:8000
UNDERSTUDY_PROJECT_ID=<PROJECT_ID from the seed>
UNDERSTUDY_DEV_USER_ID=<RAY from the seed>
```

Then start the two servers, **console last and after a fresh build** — a stale
`.next` manifest serves the page without its stylesheet, which looks exactly
like a broken product:

```bash
cd apps/api     && uvicorn app.main:app --port 8000
cd apps/reviewer && npm run build && npm run start
```

Open `http://127.0.0.1:3000` and check the Overview tile reads **4 waiting**.
If it reads 0, the console is pointed at the wrong project id.

Re-seeding produces new ids every time, so if you re-seed you must update
`.env.local` and restart the console — a restart, not a rebuild: the console
reads the project id at request time, and only a code change needs
`npm run build` again. Budget two minutes for that; do not do it in front of
anyone.

---

## What is in the demonstration project

**Northgate DC — Building A, Level 2 Fit-Out.** Five boards across three
electrical rooms, five checks each, twenty-five items.

| Check | Criticality | Traced to |
|---|---|---|
| Filler plate in every spare position | quality | 26 24 13 - 2.4.C |
| Arc flash label readable from standing position | **safety** | 26 05 00 - 1.8.B |
| Typed circuit directory naming every way | quality | 26 24 13 - 3.3.A |
| Nameplate matches the scheduled tag | quality | 26 05 00 - 2.9.A |
| Grounding conductor on its own lug, torque marked | **safety** | 26 05 26 - 3.2.D |

Every check carries worked examples: what right looks like, and — more of them —
what the near misses look like. Anybody can spot an absent label. What a green
inspector walks past is the one that is fitted, faded, and down by the plinth.

**Two reviewers.** Ray Okafor writes up his passes; Helen Barrow does not always.
That is why the labelling-rate tile reads 100% against 50%.

**Two learners.** Jordan Pike is three weeks in: strong on the obvious misses,
weak on the subtle ones. Sam Ferreira is a superintendent learning what the
inspection is actually looking for. Their agreement figures say so, per kind of
check, which is the point.

**Four items still waiting**, two of them safety, so the queue has something in
it. **Four items still open** on PP-2E in Electrical Room 2-03, for the live
walk.

---

## The demonstration

### Act one — the walk (3 minutes)

From `apps/field`:

```bash
npm run demo -- walk <PROJECT_ID> <JORDAN> <ASSET_PP_2E>
```

This is the field app's own code — its walk, its outbox, its sync — driven from
a terminal because the app itself wants a phone. It prints seven steps. Stop
after step five.

What to draw attention to, in order:

1. **The walk is compiled, not typed up.** Three items at this stop, each one a
   requirement with a clause number behind it.
2. **The worked examples come down with the walk.** One right, two wrong,
   captioned. They are on the phone before it loses signal, because that is
   where the learner needs them — at the equipment, in a basement.
3. **The call comes before the camera.** Jordan commits to *pass*. This is the
   record everything else rests on: a checklist you photograph measures
   photography, not judgement.
4. **The photograph goes in an outbox.** Nothing leaves the phone until the
   server acknowledges it, and nothing is deleted from it until then either.

### Act two — the ruling (3 minutes)

Switch to the console at `http://127.0.0.1:3000`.

1. **Overview.** Four numbers. Linger on the last one: the share of passes
   carrying a note worth reading. It is 50% for one reviewer. That number is the
   one that decays quietly, and it is on the front page on purpose.
2. **Review queue.** Safety items first, always. The banner says why.
3. **Open the PP-2E grounding item** — the one that just arrived. The
   photograph, the requirement in plain words, why it matters, the clause it
   came from, the rule-set version.
4. **Rule it Fail**, with a note: *"No torque stripe on two of the three lugs.
   Landed is not torqued — if there is no mark you cannot tell."*

Worth saying out loud while the safety banner is on screen: a safety item can
never clear on its own, in any version of this product. It is a database
trigger, not a policy document.

### Optional — delivery to CxAlloy (2 minutes)

Only if somebody asks how results reach the system of record. On the Delivery
page: **Build a package** (it counts the rulings waiting), **Download** the zip,
open it. A worklist to type from, the failures separately, the photographs named
by asset and check. Then **I have entered these** — which asks once more, because
it clears the undelivered count for everybody and nothing here can verify it.

The point to make while the zip is open: there is no write to CxAlloy anywhere in
this product. Our access is read only, so the platform's job ends at handing a
person a package they can work from, and at keeping an honest count of what has
not been entered yet.

### Act three — the loop closes (4 minutes)

Back in the terminal:

```bash
npm run demo -- feedback <PROJECT_ID> <JORDAN>
```

1. **The ruling reaches the person who took the photograph**, beside their own
   photograph and the rule it was judged against. That was the open end of the
   loop until recently; a tech could walk a building for a month and learn
   nothing from any of it.
2. **Agreement, per kind of check.** Jordan is 100% on filler plates and
   directories, 67% on arc flash labels, 33% on grounding. That is not a score
   on a person. It is a map of what to teach them next, and it is computed from
   calls they committed to before they knew the answer.

Then stop. That last table is the product.

---

## Questions that will come, and the honest answers

**"Does it decide anything itself?"** No. Phase 1 routes every item to a
person. No computer vision, no auto-clear, nothing. The photographs and the
rulings being collected now are what a Phase 2 grader would have to be measured
against — and the exit metrics are written down before any of that is built.

**"Does it write to CxAlloy?"** No. Our access is read only. Rulings queue for
somebody to enter by hand, and the Delivery page counts what is waiting. CxAlloy
stays the system of record; nothing here claims to be.

**"Who can see the photographs?"** A reviewer or an admin, anything; anybody
else, only what they captured themselves. There is no per-project membership in
the schema yet, so a reviewer's reach is every project — that is open question
Q28 and it is written down, not hidden.

**"How long did this take?"** Say it plainly. The framework is built and tested;
what it has not had is a real project's documents run through it.

---

## Rough edges — know them before somebody finds them

- **The Delivery page works now — you can click it.** Build a package, download
  the zip, confirm it. Worth doing live if the room cares about CxAlloy: the zip
  holds a worklist to type from, the failures on their own sheet, and the
  photographs. One caveat for the demo, not a defect: confirming clears the
  undelivered count, so the Overview tile drops to zero and stays there. Do it
  last, or re-seed afterwards.
- **Kinds of check display as squashed keys** — `arcflashlabel`, not "arc flash
  label". The key is normalised for matching and there is no display name beside
  it yet. Cosmetic, and visible on the agreement table.
- **The reviewer is not shown the learner's call.** Deliberate: a reviewer who
  knows the learner said *pass* is no longer an independent second opinion, and
  the agreement number would be measuring anchoring. If asked, that is the
  answer.
- **Object storage in the sandbox is in-memory.** Restart it and every
  photograph is gone; the console then reports that the photo has not been
  uploaded. Re-seed to recover.
- **Re-seeding changes every id.** `.env.local` and the console both need
  updating. Never mid-demonstration.

---

## Resetting between runs

```bash
cd apps/api
dropdb -h localhost -U understudy understudy_demo
createdb -h localhost -U understudy understudy_demo
alembic upgrade head && python scripts/seed_demo.py
# put the new project id and Ray's id in apps/reviewer/.env.local, then restart
# the console — no rebuild needed unless the code changed
```

Read the ids back out of the database rather than off an older run's notes. A
stale project id points the console at something that is not there, and an
empty dashboard in front of an audience looks like a dead product:

```bash
psql -h localhost -U understudy understudy_demo -c \
  "select id, name from project order by created_at desc limit 1"
```
