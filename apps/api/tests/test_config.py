"""The dev-identity guard is a safety rule, so it is tested like one."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Environment, Settings


@pytest.mark.parametrize("environment", [Environment.STAGING, Environment.PRODUCTION])
def test_dev_identity_refused_outside_development(environment: Environment) -> None:
    with pytest.raises(ValidationError, match="auth_dev_identity_enabled"):
        Settings(environment=environment, auth_dev_identity_enabled=True)


@pytest.mark.parametrize("environment", [Environment.DEVELOPMENT, Environment.TEST])
def test_dev_identity_allowed_in_development_and_test(environment: Environment) -> None:
    settings = Settings(environment=environment, auth_dev_identity_enabled=True)
    assert settings.auth_dev_identity_enabled is True


@pytest.mark.parametrize("environment", [Environment.STAGING, Environment.PRODUCTION])
def test_real_identity_required_environments_start_without_dev_identity(
    environment: Environment,
) -> None:
    settings = Settings(environment=environment, auth_dev_identity_enabled=False)
    assert settings.auth_dev_identity_enabled is False
