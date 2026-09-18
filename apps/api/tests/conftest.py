from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import Environment, Settings
from app.main import create_app

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://understudy@127.0.0.1:55432/understudy_test"


@pytest.fixture
def settings() -> Settings:
    return Settings(environment=Environment.TEST, auth_dev_identity_enabled=True)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """A migrated database, or a skip.

    The schema under test is the one Alembic produces, not one built from
    model metadata: a migration that does not match the models is exactly the
    bug worth catching, and create_all would hide it. The database-level
    guards live only in the migration, so create_all would not test them at all.
    """
    eng = create_engine(database_url, future=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        # Skipping is right on a laptop with nothing running. It is wrong in
        # CI: a misconfigured URL would silently delete every safety-invariant
        # test from the run and the build would still go green.
        if os.environ.get("REQUIRE_TEST_DATABASE") == "1":
            pytest.fail(
                f"REQUIRE_TEST_DATABASE is set but no database is reachable at "
                f"{database_url}: {exc}"
            )
        pytest.skip(f"No test database at {database_url}: {exc}")

    from alembic.config import Config

    from alembic import command

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    yield eng
    eng.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    """Each test runs inside a transaction that is rolled back afterwards."""
    conn = engine.connect()
    transaction = conn.begin()
    try:
        yield conn
    finally:
        transaction.rollback()
        conn.close()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
