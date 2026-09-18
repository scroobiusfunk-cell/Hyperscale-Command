"""predictions and reference images

The two pieces the teaching purpose needs and the capture-first build never had:
the learner's own call recorded before the reveal, and examples of what good and
wrong actually look like.

`prediction` is append-only, enforced by the same trigger the other
append-only tables use. That trigger is the whole point of the table: an
agreement number computed from calls a learner could edit after seeing the
answer would be worthless.

Revision ID: 7bd41e0c9a52
Revises: 3282255359f6
Create Date: 2026-09-18 11:04:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7bd41e0c9a52"
down_revision: str | None = "3282255359f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Created by create_table below, so referenced with create_type=False anywhere
# a second table would otherwise try to create them again.
predicted_verdict = postgresql.ENUM(
    "pass", "fail", "unsure", name="predicted_verdict", create_type=False
)
reference_kind = postgresql.ENUM("good", "wrong", name="reference_kind", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    predicted_verdict.create(bind, checkfirst=True)
    reference_kind.create(bind, checkfirst=True)

    op.create_table(
        "prediction",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("checklist_item_id", sa.UUID(), nullable=False),
        sa.Column("predicted_by", sa.UUID(), nullable=False),
        sa.Column("verdict", predicted_verdict, nullable=False),
        sa.Column(
            "reason",
            sa.String(length=200),
            nullable=True,
            comment=(
                "Which disqualifier the learner believes they saw, from the item's own "
                "short list. Null on a pass or when they were unsure."
            ),
        ),
        sa.Column(
            "note",
            sa.Text(),
            nullable=True,
            comment="Optional free text. Nothing depends on it.",
        ),
        sa.Column("item_type", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["checklist_item.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["predicted_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checklist_item_id", "predicted_by", name="uq_prediction_item_person"),
    )
    op.create_index("ix_prediction_person_created", "prediction", ["predicted_by", "created_at"])
    op.create_index("ix_prediction_item", "prediction", ["checklist_item_id"])

    # The reason this table is trustworthy. fie_forbid_mutation() already exists
    # from 0001; this only attaches it.
    op.execute(
        """
        CREATE TRIGGER trg_prediction_append_only
        BEFORE UPDATE OR DELETE ON prediction
        FOR EACH ROW EXECUTE FUNCTION fie_forbid_mutation();
        """
    )

    op.create_table(
        "reference_image",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("item_type", sa.String(length=100), nullable=False),
        sa.Column("kind", reference_kind, nullable=False),
        sa.Column(
            "caption",
            sa.Text(),
            nullable=False,
            comment=(
                "What to notice, in plain words. An example with no caption is a "
                "photograph; with one it is a lesson. Required for that reason."
            ),
        ),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sourced_from_evidence_id", sa.UUID(), nullable=True),
        sa.Column("added_by", sa.UUID(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("byte_size > 0", name="ck_reference_image_byte_size_positive"),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_reference_image_content_hash_is_sha256"
        ),
        sa.CheckConstraint("length(btrim(caption)) > 0", name="ck_reference_image_caption_present"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sourced_from_evidence_id"], ["evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["added_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reference_image_lookup", "reference_image", ["project_id", "item_type", "kind"]
    )

    # prediction_made joins the device's event log.
    op.execute("ALTER TYPE sync_event_type ADD VALUE IF NOT EXISTS 'prediction_made'")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_prediction_append_only ON prediction")
    op.drop_index("ix_reference_image_lookup", table_name="reference_image")
    op.drop_table("reference_image")
    op.drop_index("ix_prediction_item", table_name="prediction")
    op.drop_index("ix_prediction_person_created", table_name="prediction")
    op.drop_table("prediction")
    # Postgres leaves the types behind when their tables go; drop them by hand
    # or the next upgrade on this database fails with "type already exists".
    op.execute("DROP TYPE IF EXISTS reference_kind")
    op.execute("DROP TYPE IF EXISTS predicted_verdict")
    # sync_event_type keeps prediction_made: Postgres cannot remove an enum
    # value, and a stored event naming it must stay readable.
