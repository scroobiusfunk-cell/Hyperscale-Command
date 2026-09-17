"""rule set versioning

Adds the RuleSet table and makes requirement identity version-aware.

The architecture doc says Requirement.id is "stable across versions where the
requirement is unchanged", which means id alone cannot be the primary key: a
spec revision produces a new rule set carrying the same requirement id. Identity
is (id, ruleset_version), and ChecklistItem already records both, so its foreign
key becomes composite.

Autogenerate cannot emit the primary key swap (it has no name for the existing
unnamed constraint) and would have produced a migration that fails, so the
ordering below is hand-written.

Revision ID: 4ed9943aba2a
Revises: 4c3e25ca5a2f
Create Date: 2026-09-17 19:38:55.166233
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4ed9943aba2a"
down_revision: str | None = "4c3e25ca5a2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rule_set",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "superseded", name="rule_set_status"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("supersedes_id", sa.UUID(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status <> 'published' OR (published_by IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_rule_set_published_by_a_person",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["rule_set.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version", name="uq_rule_set_project_version"),
    )

    # Drop the foreign keys that point at requirement.id before the key changes
    # underneath them.
    op.drop_constraint("checklist_item_requirement_id_fkey", "checklist_item", type_="foreignkey")
    op.drop_constraint("labeled_example_requirement_id_fkey", "labeled_example", type_="foreignkey")

    op.add_column("requirement", sa.Column("rule_set_id", sa.UUID(), nullable=False))
    op.add_column(
        "requirement",
        sa.Column(
            "approved_by",
            sa.UUID(),
            nullable=True,
            comment=(
                "The curator who approved this requirement. Not in the architecture doc's "
                "field table, but a safety requirement that went live with nobody's name on "
                "it cannot be defended later."
            ),
        ),
    )
    op.add_column(
        "requirement", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_requirement_approved_by_a_person",
        "requirement",
        "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_requirement_approved_by",
        "requirement",
        "app_user",
        ["approved_by"],
        ["id"],
        ondelete="RESTRICT",
    )

    # The identity change itself.
    op.drop_constraint("requirement_pkey", "requirement", type_="primary")
    op.create_primary_key("pk_requirement", "requirement", ["id", "ruleset_version"])

    op.create_foreign_key(
        "fk_requirement_rule_set",
        "requirement",
        "rule_set",
        ["rule_set_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_checklist_item_requirement",
        "checklist_item",
        "requirement",
        ["requirement_id", "ruleset_version"],
        ["id", "ruleset_version"],
        ondelete="RESTRICT",
    )

    # labeled_example.requirement_id keeps no foreign key: the checklist item it
    # points at already guarantees the requirement exists.
    op.alter_column(
        "labeled_example",
        "requirement_id",
        existing_type=sa.UUID(),
        comment=(
            "Copied from the checklist item. No foreign key: requirement identity is "
            "(id, ruleset_version) and the checklist item already guarantees integrity."
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "requirement",
        "id",
        existing_type=sa.UUID(),
        comment=(
            "Carried forward unchanged into a new rule set version when the requirement "
            "did not change."
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "requirement", "id", existing_type=sa.UUID(), comment=None, existing_nullable=False
    )
    op.alter_column(
        "labeled_example",
        "requirement_id",
        existing_type=sa.UUID(),
        comment=None,
        existing_nullable=False,
    )

    op.drop_constraint("fk_checklist_item_requirement", "checklist_item", type_="foreignkey")
    op.drop_constraint("fk_requirement_rule_set", "requirement", type_="foreignkey")

    op.drop_constraint("pk_requirement", "requirement", type_="primary")
    op.create_primary_key("requirement_pkey", "requirement", ["id"])

    op.drop_constraint("fk_requirement_approved_by", "requirement", type_="foreignkey")
    op.drop_constraint("ck_requirement_approved_by_a_person", "requirement", type_="check")
    op.drop_column("requirement", "approved_at")
    op.drop_column("requirement", "approved_by")
    op.drop_column("requirement", "rule_set_id")

    op.create_foreign_key(
        "labeled_example_requirement_id_fkey",
        "labeled_example",
        "requirement",
        ["requirement_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "checklist_item_requirement_id_fkey",
        "checklist_item",
        "requirement",
        ["requirement_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_table("rule_set")
    op.execute("DROP TYPE IF EXISTS rule_set_status")
