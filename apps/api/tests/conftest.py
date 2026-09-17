from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Environment, Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(environment=Environment.TEST, auth_dev_identity_enabled=True)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
