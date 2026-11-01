"""Settings for the Working Paper Binder backend.

Values come from the environment and from ``backend/.env`` (see ``.env.example``). Nothing in
this module opens a connection. Two guards live here because they are configuration, not
features: a database URL may only name the Binder's own databases (architecture D5), and
production refuses a development identity (D8).
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

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


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def spine_url_is_secure(url: str) -> bool:
    """https anywhere, or plain http only to the loopback interface (D29)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" or host in LOOPBACK_HOSTS or host.startswith("127.")


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
    # Who is acting (spec 7: sign-off is an authenticated action; D8, D24).
    #   dev     the fixed identity in OAK_DEV_USER; development and tests only
    #   header  the identity an authenticating reverse proxy places in OAK_AUTH_HEADER on
    #           every request, after it has signed the user in; the Binder trusts that
    #           header and verifies nothing itself, so the proxy must strip any copy a client
    #           sends and must be the only route to the API
    auth: Literal["dev", "header"] = "dev"
    auth_header: str = "X-Authenticated-User"
    # In header mode, the only addresses whose identity header is believed: the proxy's,
    # as a comma-separated list of IPs or networks (10.0.0.5, 10.0.0.0/24, ::1). Empty
    # means any peer, which production refuses.
    trusted_proxies: str = ""
    dev_user: str | None = None
    attachments_dir: Path = Path("../var/attachments")
    max_upload_bytes: int = 26_214_400
    # Where attachment bytes live (D23, D27). "local" is the write-once directory above and
    # the default. "vault" is the firm's Google Drive folder:
    #   OAK_VAULT_URL          the Drive API base, https://www.googleapis.com/drive/v3
    #   OAK_VAULT_CONTAINER    the vault folder's id
    #   OAK_VAULT_CREDENTIAL   path of the refresh-token file vault_login writes
    #   OAK_VAULT_CLIENT_FILE  path of the Desktop OAuth client JSON
    # Both files live under the git-ignored backend/secrets and are never printed.
    store: Literal["local", "vault"] = "local"
    vault_url: str | None = None
    vault_credential: str | None = None
    vault_container: str | None = None
    vault_client_file: str | None = None
    # The Financial Spine (D29): the service root, e.g. http://127.0.0.1:8000, read-only.
    # Unset means no Spine: every Spine-dependent feature says so instead of failing. An
    # optional bearer credential is sent when set; the Spine has no authentication today.
    spine_url: str | None = None
    spine_credential: str | None = None
    # Generated-paper intake (D31). Under OAK_AUTH=header only the identities listed here,
    # comma-separated, may deliver papers; none listed means no intake. An optional bearer
    # the module must present on the intake endpoint. The provenance block's size cap.
    intake_identities: str = ""
    intake_credential: str | None = None
    max_provenance_bytes: int = 1_048_576

    def intake_identity_set(self) -> frozenset[str]:
        return frozenset(p.strip() for p in self.intake_identities.split(",") if p.strip())

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _binder_database_only(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        name = f"OAK_{(info.field_name or 'database_url').upper()}"
        return check_binder_url(value, allowed=frozenset({APP_DATABASE, TEST_DATABASE}), name=name)

    @field_validator("spine_url")
    @classmethod
    def _spine_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlparse(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(
                "OAK_SPINE_URL must be an http:// or https:// URL with a host, "
                "for example http://127.0.0.1:8000"
            )
        return value.strip().rstrip("/")

    @field_validator("test_database_url", "test_app_database_url")
    @classmethod
    def _test_database_only(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        name = f"OAK_{(info.field_name or 'test_database_url').upper()}"
        return check_binder_url(value, allowed=frozenset({TEST_DATABASE}), name=name)

    @model_validator(mode="after")
    def _vault_guard(self) -> Settings:
        if self.store != "vault":
            return self
        missing = [
            name
            for name, value in (
                ("OAK_VAULT_URL", self.vault_url),
                ("OAK_VAULT_CREDENTIAL", self.vault_credential),
                ("OAK_VAULT_CONTAINER", self.vault_container),
                ("OAK_VAULT_CLIENT_FILE", self.vault_client_file),
            )
            if not (value or "").strip()
        ]
        if missing:
            raise ValueError(
                f"OAK_STORE=vault needs {', '.join(missing)}; "
                "set them, or use OAK_STORE=local (architecture D23, D27)"
            )
        return self

    def trusted_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return [
            ipaddress.ip_network(part.strip(), strict=False)
            for part in self.trusted_proxies.split(",")
            if part.strip()
        ]

    @model_validator(mode="after")
    def _auth_guard(self) -> Settings:
        # dev mode without OAK_DEV_USER is allowed outside production: the identity
        # dependency answers 503 until it is set.
        if self.auth == "header" and not self.auth_header.strip():
            raise ValueError("OAK_AUTH=header needs OAK_AUTH_HEADER, the header the proxy sets")
        try:
            self.trusted_networks()
        except ValueError as exc:
            raise ValueError(
                "OAK_TRUSTED_PROXIES must be a comma-separated list of IP addresses or networks"
            ) from exc
        return self

    @model_validator(mode="after")
    def _production_guard(self) -> Settings:
        if self.env != "production":
            return self
        if self.dev_user:
            raise ValueError(
                "OAK_DEV_USER must not be set when OAK_ENV=production: "
                "sign-off needs real authentication (architecture D8)"
            )
        if self.auth == "dev":
            raise ValueError(
                "OAK_AUTH=dev is not allowed when OAK_ENV=production: set OAK_AUTH=header "
                "behind an authenticating proxy (architecture D24)"
            )
        if not self.trusted_networks():
            raise ValueError(
                "OAK_TRUSTED_PROXIES must list the proxy's address(es) when OAK_ENV=production: "
                "otherwise anyone who can reach the API can name themselves (architecture D24)"
            )
        if self.spine_url and not spine_url_is_secure(self.spine_url):
            raise ValueError(
                "OAK_SPINE_URL must use https:// when OAK_ENV=production unless the Spine is "
                "on the loopback interface (architecture D29)"
            )
        if make_url(self.database_url).database != APP_DATABASE:
            raise ValueError(f"OAK_DATABASE_URL must name {APP_DATABASE} when OAK_ENV=production")
        return self


def get_settings() -> Settings:
    """Read settings from the environment and ``backend/.env``."""
    return Settings()
