"""one verdict vocabulary across both repos

R-00. Three enums said almost the same thing in slightly different words:
`grader_verdict` (pass/fail/insufficient_evidence), `ruling_verdict`
(pass/fail/recapture_requested) and `predicted_verdict` (pass/fail/unsure). The
Rule Registry says `pass | fail | indeterminate | not_visible`. Four vocabularies
for one idea, and no way to count a reviewer's "send it back" beside a learner's
"I do not know" even though both are the same shape of answer.

All three collapse to `verdict`, with the distinction kept in `verdict_reason`,
which is set exactly when the verdict is `indeterminate`.

Three things about this migration are not obvious.

**The append-only triggers refuse the backfill.** `ruling` and `prediction` both
carry a row-level trigger that raises on UPDATE, which is the point of them. DDL
does not fire row triggers, so the `ALTER COLUMN ... TYPE ... USING` is fine, but
populating `verdict_reason` from the old value is an UPDATE and would be refused.
The triggers are disabled for the length of that statement and re-enabled
immediately. This is the one place that is allowed to do it, and it is why the
whole migration runs inside a single transaction: a failure part way leaves the
triggers on, because the disable rolls back with everything else.

**Order matters.** `verdict_reason` is filled from the old verdict *before* the
verdict column is retyped, because afterwards the old value is gone.

**One shared type, four columns.** `verdict` is created once. Every later
`postgresql.ENUM` naming it passes `create_type=False`, per the trap in
alembic/README.md: a second table re-creating an existing type fails.

Revision ID: 4f1c7a0b83d2
Revises: b41e77cd2f08
Create Date: 2026-09-20 11:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "4f1c7a0b83d2"
down_revision: str | None = "b41e77cd2f08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: table -> (old type name, the append-only trigger to hold off, old values)
TABLES = {
    "grader_result": ("grader_verdict", None),
    "ruling": ("ruling_verdict", "trg_ruling_append_only"),
    "prediction": ("predicted_verdict", "trg_prediction_append_only"),
    "labeled_example": ("ruling_verdict", None),
}

#: The old verdict values that become `indeterminate` plus a reason.
RETIRED = ("insufficient_evidence", "recapture_requested", "unsure")

OLD_VALUES = {
    "grader_verdict": ("pass", "fail", "insufficient_evidence"),
    "ruling_verdict": ("pass", "fail", "recapture_requested"),
    "predicted_verdict": ("pass", "fail", "unsure"),
}


#: Column comments, kept identical to the models. `test_models_and_migration_agree`
#: compares them, so a comment that drifts fails the build rather than quietly
#: leaving psql describing the schema differently from the code.
COMMENTS = {
    ("grader_result", "verdict_reason"): (
        "Which kind of indeterminate. Set exactly when verdict is indeterminate; a check "
        "constraint refuses the other combinations."
    ),
    ("ruling", "verdict_reason"): (
        "`recapture_requested` where a reviewer is sending the photograph back. That is a "
        "judgement on the evidence, not the installation, so it produces no LabeledExample "
        "and the item reopens."
    ),
    ("prediction", "verdict_reason"): (
        "`unsure` where the learner said so. Excluded from the agreement rate."
    ),
    ("prediction", "disqualifier"): (
        "Which disqualifier the learner believes they saw, from the item's own short list. "
        "Null on a pass or when they were unsure. Renamed from `reason` in R-00: a table "
        "cannot carry two fields called reason meaning unrelated things."
    ),
    ("labeled_example", "human_verdict"): (
        "Always pass or fail. A labelled example is a definite judgement about the "
        "installation, so the indeterminate verdicts cannot produce one: a recapture judges "
        "the photograph, and a grader that could not tell has nothing to teach."
    ),
}

OLD_COMMENTS = {
    ("prediction", "reason"): (
        "Which disqualifier the learner believes they saw, from the item's own short list. "
        "Null on a pass or when they were unsure."
    ),
}


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.execute(
        f"CREATE TYPE verdict AS ENUM ({_quoted(('pass', 'fail', 'indeterminate', 'not_visible'))})"
    )
    op.execute(f"CREATE TYPE verdict_reason AS ENUM ({_quoted(RETIRED)})")

    # Dropped before the retype, not after. Postgres re-checks a CHECK constraint
    # when the column's type changes, and this one names 'insufficient_evidence',
    # a value of the type being retired: the comparison no longer has an operator.
    op.execute(
        "ALTER TABLE grader_result DROP CONSTRAINT ck_grader_result_insufficient_is_not_confident"
    )

    for table, (_old_type, trigger) in TABLES.items():
        column = "human_verdict" if table == "labeled_example" else "verdict"

        if table != "labeled_example":
            op.execute(f"ALTER TABLE {table} ADD COLUMN verdict_reason verdict_reason")
            # The backfill is an UPDATE, which the append-only trigger exists to
            # refuse. Held off for this statement only; the transaction puts it
            # back even if something below fails.
            if trigger:
                op.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
            op.execute(
                f"""
                UPDATE {table}
                   SET verdict_reason = {column}::text::verdict_reason
                 WHERE {column}::text IN ({_quoted(RETIRED)})
                """
            )
            if trigger:
                op.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")

        op.execute(
            f"""
            ALTER TABLE {table}
            ALTER COLUMN {column} TYPE verdict
            USING (CASE WHEN {column}::text IN ({_quoted(RETIRED)})
                        THEN 'indeterminate' ELSE {column}::text END)::verdict
            """
        )

    for table in ("grader_result", "ruling", "prediction"):
        op.execute(
            f"""
            ALTER TABLE {table} ADD CONSTRAINT ck_{table}_reason_iff_indeterminate
            CHECK ((verdict = 'indeterminate') = (verdict_reason IS NOT NULL))
            """
        )

    op.execute(
        """
        ALTER TABLE grader_result ADD CONSTRAINT ck_grader_result_insufficient_is_not_confident
        CHECK (verdict <> 'indeterminate' OR confidence <= 0.5)
        """
    )
    op.execute(
        """
        ALTER TABLE labeled_example ADD CONSTRAINT ck_labeled_example_verdict_is_definite
        CHECK (human_verdict IN ('pass', 'fail'))
        """
    )

    # `reason` on prediction means which disqualifier the learner thought they
    # saw. Two fields called reason on one table, meaning unrelated things, is
    # the ambiguity this whole change exists to remove.
    op.execute("ALTER TABLE prediction RENAME COLUMN reason TO disqualifier")

    for (table, column), comment in COMMENTS.items():
        op.execute(f"COMMENT ON COLUMN {table}.{column} IS $c${comment}$c$")

    for old_type in ("grader_verdict", "ruling_verdict", "predicted_verdict"):
        op.execute(f"DROP TYPE {old_type}")


def downgrade() -> None:
    for table, column in COMMENTS:
        op.execute(f"COMMENT ON COLUMN {table}.{column} IS NULL")
    op.execute("ALTER TABLE prediction RENAME COLUMN disqualifier TO reason")
    for (table, column), comment in OLD_COMMENTS.items():
        op.execute(f"COMMENT ON COLUMN {table}.{column} IS $c${comment}$c$")
    op.execute("ALTER TABLE labeled_example DROP CONSTRAINT ck_labeled_example_verdict_is_definite")
    op.execute(
        "ALTER TABLE grader_result DROP CONSTRAINT ck_grader_result_insufficient_is_not_confident"
    )
    for table in ("grader_result", "ruling", "prediction"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT ck_{table}_reason_iff_indeterminate")

    for old_type, values in OLD_VALUES.items():
        op.execute(f"CREATE TYPE {old_type} AS ENUM ({_quoted(values)})")

    for table, (old_type, trigger) in TABLES.items():
        column = "human_verdict" if table == "labeled_example" else "verdict"
        # Going back, an indeterminate row becomes whichever old value its reason
        # names. labeled_example never held one, so it maps straight across.
        if table == "labeled_example":
            using = f"{column}::text::{old_type}"
        else:
            using = (
                f"(CASE WHEN {column} = 'indeterminate' THEN verdict_reason::text "
                f"ELSE {column}::text END)::{old_type}"
            )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {old_type} USING {using}")
        if table != "labeled_example":
            if trigger:
                op.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
            op.execute(f"ALTER TABLE {table} DROP COLUMN verdict_reason")
            if trigger:
                op.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")

    op.execute(
        """
        ALTER TABLE grader_result ADD CONSTRAINT ck_grader_result_insufficient_is_not_confident
        CHECK (verdict <> 'insufficient_evidence' OR confidence <= 0.5)
        """
    )
    # Both new types go, or a rerun of the upgrade fails on CREATE TYPE.
    op.execute("DROP TYPE verdict")
    op.execute("DROP TYPE verdict_reason")
