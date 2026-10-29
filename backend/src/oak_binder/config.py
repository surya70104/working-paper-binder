"""Settings for the Working Paper Binder backend.

Values come from the environment and from ``backend/.env`` (see ``.env.example``). Nothing in
this module opens a connection. Two guards live here because they are configuration, not
features: a database URL may only name the Binder's own databases (architecture D5), and
production refuses a development identity (D8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

APP_DATABASE = "oak_binder"
TEST_DATABASE = "oak_binder_test"
DRIVER = "postgresql+psycopg"


def check_binder_url(url: str, *, allowed: frozenset[str], name: str) -> str:
    """Return ``url`` if it uses the psycopg driver, gives host and port explicitly, and
    names one of the Binder's own databases. Raise ``ValueError`` otherwise."""
    if not url:
        raise ValueError(f"{name} is not set: copy backend\\.env.example to backend\\.env")
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise ValueError(f"{name} is not a valid database URL") from exc
    if parsed.drivername != DRIVER:
        raise ValueError(f"{name} must start with {DRIVER}://")
    if not parsed.host or parsed.port is None:
        raise ValueError(f"{name} must give the host and port explicitly")
    if parsed.database not in allowed:
        raise ValueError(
            f"{name} must name one of {sorted(allowed)}, not {parsed.database!r}: "
            "the Binder never connects to any other database"
        )
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OAK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    env: Literal["development", "test", "production"] = "development"
    # Empty by default so Settings() needs no arguments; the validator refuses an empty value.
    database_url: str = ""
    migration_database_url: str | None = None
    test_database_url: str | None = None
    test_app_database_url: str | None = None
    dev_user: str | None = None
    attachments_dir: Path = Path("../var/attachments")
    max_upload_bytes: int = 26_214_400

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _binder_database_only(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        name = f"OAK_{(info.field_name or 'database_url').upper()}"
        return check_binder_url(value, allowed=frozenset({APP_DATABASE, TEST_DATABASE}), name=name)

    @field_validator("test_database_url", "test_app_database_url")
    @classmethod
    def _test_database_only(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        name = f"OAK_{(info.field_name or 'test_database_url').upper()}"
        return check_binder_url(value, allowed=frozenset({TEST_DATABASE}), name=name)

    @model_validator(mode="after")
    def _production_guard(self) -> Settings:
        if self.env != "production":
            return self
        if self.dev_user:
            raise ValueError(
                "OAK_DEV_USER must not be set when OAK_ENV=production: "
                "sign-off needs real authentication (architecture D8)"
            )
        if make_url(self.database_url).database != APP_DATABASE:
            raise ValueError(f"OAK_DATABASE_URL must name {APP_DATABASE} when OAK_ENV=production")
        return self


def get_settings() -> Settings:
    """Read settings from the environment and ``backend/.env``."""
    return Settings()
