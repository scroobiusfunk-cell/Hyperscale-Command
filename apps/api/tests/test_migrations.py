"""The migration is the schema, so it gets tested like one."""

from __future__ import annotations

from sqlalchemy import Connection, inspect, text

EXPECTED_TABLES = {
    "app_user",
    "asset",
    "asset_alias",
    "asset_submittal",
    "capture_recipe",
    "checklist_item",
    "evidence",
    "grader_result",
    "labeled_example",
    "project",
    "requirement",
    "ruling",
    "source_document",
}


def test_migration_creates_every_expected_table(connection: Connection) -> None:
    tables = set(inspect(connection).get_table_names())
    assert tables >= EXPECTED_TABLES


def test_models_and_migration_agree(connection: Connection) -> None:
    """An autogenerate diff against the migrated database must come back empty.

    This is the check that catches a model changed without a migration, which
    CLAUDE.md forbids outright.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app import models  # noqa: F401  (populates metadata)
    from app.db import Base

    context = MigrationContext.configure(connection)
    diff = compare_metadata(context, Base.metadata)
    assert diff == [], f"models and migration disagree: {diff}"


def test_pgvector_extension_is_available(connection: Connection) -> None:
    installed = connection.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    assert installed == 1


def test_evidence_has_no_verdict_column(connection: Connection) -> None:
    """Evidence is never a judgment. The absence of this column is the guard."""
    columns = {c["name"] for c in inspect(connection).get_columns("evidence")}
    assert not columns & {"verdict", "passed", "result", "quality"}
