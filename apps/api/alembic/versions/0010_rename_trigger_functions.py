"""rename the trigger functions off the old product name

The last `fie` identifiers. They are invisible to everyone except somebody
reading `\\df` in psql, which is exactly why they were left until last.

`ALTER FUNCTION ... RENAME TO` is used rather than dropping and recreating,
and the distinction matters more here than anywhere else in the schema. A
trigger stores the function's OID, not its name, so a rename keeps every
existing trigger pointing at the same function and firing exactly as before.
Dropping and recreating would mint a new OID and require every trigger to be
rebuilt — and these are the triggers enforcing that rulings and predictions
are append-only and that a safety item can never auto-clear. A window where
those are absent is not worth opening to tidy a name.

Migrations 0001 and 0009 still say the old names, because they already ran and
applied history is not rewritten. A database built from scratch creates them
under the old names and arrives here to be renamed, which is the same end
state.

Revision ID: b41e77cd2f08
Revises: 7bd41e0c9a52
Create Date: 2026-09-18 12:41:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b41e77cd2f08"
down_revision: str | None = "7bd41e0c9a52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RENAMES = (
    ("fie_forbid_mutation", "understudy_forbid_mutation"),
    ("fie_forbid_safety_auto_clear", "understudy_forbid_safety_auto_clear"),
)


def _rename(old: str, new: str) -> None:
    # Guarded so the migration is safe on a database where a previous attempt
    # got part way, and on one restored from a dump taken either side of it.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = '{old}')
               AND NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = '{new}') THEN
                ALTER FUNCTION {old}() RENAME TO {new};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    for old, new in RENAMES:
        _rename(old, new)


def downgrade() -> None:
    for old, new in RENAMES:
        _rename(new, old)
