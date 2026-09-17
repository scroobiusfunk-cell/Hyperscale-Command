# Migrations

`alembic upgrade head` via `make migrate`. New migration: `make revision m="..."`.

Autogenerate gets the tables right and the enums wrong. Three traps have bitten
this project already, all of them the same shape — Postgres enum types have a
lifecycle of their own, separate from the tables that use them:

| Situation | What autogenerate does | What you have to add |
| --- | --- | --- |
| A new table with a new enum column | Creates the type correctly | Nothing on upgrade. On **downgrade**, `DROP TYPE` after the table, or a later upgrade fails with "type already exists" |
| `add_column` with a new enum | Emits the column and *not* the type | `postgresql.ENUM(..., create_type=False).create(op.get_bind(), checkfirst=True)` before the `add_column` |
| A new table reusing an existing enum | Emits a fresh `sa.Enum`, which tries to `CREATE TYPE` a second time | Replace it with `postgresql.ENUM(name="...", create_type=False)` |

The reason all three survive a green test run is that a **fresh** database often
works while an **existing** one fails, or the reverse. So test every path, not
just the one you are on:

```
alembic upgrade head      # incremental, from whatever you already have
alembic downgrade -1      # one step back
alembic upgrade head      # and forward again
alembic downgrade base    # all the way down
alembic upgrade head      # and all the way up
```

CI runs the full down-and-up on every build. `tests/test_migrations.py` also
asserts that an autogenerate diff against the migrated database comes back
empty, so a model changed without a migration fails the build.
