"""Application settings, loaded from the environment.

The dev-identity guard in `Settings` is the one piece of policy that lives
here rather than in the policy layer: a reviewer's ruling on a `safety` item
has to carry a real person's identity, so an environment that can mint fake
identities must never start outside development.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+psycopg://understudy:understudy_local_dev@localhost:5432/understudy"
    )
    redis_url: str = "redis://localhost:6379/0"

    storage_endpoint_url: str | None = None
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_region: str = "us-east-1"
    evidence_bucket: str = "understudy-evidence"
    documents_bucket: str = "understudy-documents"
    exports_bucket: str = "understudy-exports"
    reference_bucket: str = "understudy-reference"

    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    auth_dev_identity_enabled: bool = False

    # CxAlloy's API is read only; see docs/adr/0001. These configure reads.
    cxalloy_base_url: str = ""
    cxalloy_api_key: str = ""
    cxalloy_project_id: str = ""

    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""

    request_timeout_seconds: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def _refuse_dev_identity_outside_development(self) -> Settings:
        if self.auth_dev_identity_enabled and self.environment not in (
            Environment.DEVELOPMENT,
            Environment.TEST,
        ):
            raise ValueError(
                "auth_dev_identity_enabled must be false outside development. "
                "Reviewer rulings on safety items have to carry a real identity."
            )
        return self

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT


def load_settings() -> Settings:
    """Build settings from the environment.

    Not cached: tests construct `Settings` directly with overrides, and the
    worker and API each load once at startup.
    """
    return Settings()
