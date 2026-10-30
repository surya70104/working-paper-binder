"""The two configuration guards (architecture D5 and D8).

Every test builds settings through ``make_settings`` (see conftest), which reads neither
backend/.env nor the environment, so the results do not depend on the developer's machine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from oak_binder.config import Settings

BINDER = "postgresql+psycopg://oak_binder_app:x@localhost:5432/oak_binder"
BINDER_TEST = "postgresql+psycopg://oak_binder_owner:x@localhost:5432/oak_binder_test"

MakeSettings = Callable[..., Settings]


@pytest.fixture
def dev(make_settings: MakeSettings) -> MakeSettings:
    """Development settings with a valid Binder URL, overridable per test."""

    def _dev(**overrides: Any) -> Settings:
        values: dict[str, Any] = {"env": "development", "database_url": BINDER}
        values.update(overrides)
        return make_settings(**values)

    return _dev


def test_binder_database_is_accepted(dev: MakeSettings) -> None:
    assert dev().database_url == BINDER


def test_missing_database_url_is_refused(make_settings: MakeSettings) -> None:
    with pytest.raises(ValidationError, match="OAK_DATABASE_URL is not set"):
        make_settings(env="development")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://oak_app:x@localhost:5432/oak_spine",
        "postgresql+psycopg://oak_owner:x@localhost:5432/oak_spine_test",
        "postgresql+psycopg://postgres:x@localhost:5432/postgres",
    ],
)
def test_other_databases_are_refused(dev: MakeSettings, url: str) -> None:
    with pytest.raises(ValidationError, match="never connects to any other database"):
        dev(database_url=url)
    with pytest.raises(ValidationError, match="never connects to any other database"):
        dev(migration_database_url=url)


def test_test_database_url_must_be_oak_binder_test(dev: MakeSettings) -> None:
    assert dev(test_database_url=BINDER_TEST).test_database_url == BINDER_TEST
    with pytest.raises(ValidationError, match="oak_binder_test"):
        dev(test_database_url=BINDER)


def test_driver_host_and_port_are_required(dev: MakeSettings) -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        dev(database_url="postgresql://oak_binder_app:x@localhost:5432/oak_binder")
    with pytest.raises(ValidationError, match="host and port"):
        dev(database_url="postgresql+psycopg://oak_binder_app:x@localhost/oak_binder")
    with pytest.raises(ValidationError, match="not a valid database URL"):
        dev(database_url="not a url")


def test_production_refuses_dev_user(dev: MakeSettings) -> None:
    production = dict(env="production", dev_user=None, auth="header", trusted_proxies="10.0.0.5")
    assert dev(**production).env == "production"
    with pytest.raises(ValidationError, match="OAK_DEV_USER must not be set"):
        dev(**{**production, "dev_user": "dev@localhost"})


def test_store_defaults_to_local_and_vault_needs_its_settings(dev: MakeSettings) -> None:
    assert dev().store == "local"
    with pytest.raises(
        ValidationError,
        match=(
            "OAK_STORE=vault needs OAK_VAULT_URL, OAK_VAULT_CREDENTIAL, OAK_VAULT_CONTAINER, "
            "OAK_VAULT_CLIENT_FILE"
        ),
    ):
        dev(store="vault")
    with pytest.raises(
        ValidationError,
        match="needs OAK_VAULT_CREDENTIAL, OAK_VAULT_CONTAINER, OAK_VAULT_CLIENT_FILE",
    ):
        dev(store="vault", vault_url="https://vault.example.test")
    # A blank value counts as missing.
    with pytest.raises(
        ValidationError,
        match="needs OAK_VAULT_CREDENTIAL, OAK_VAULT_CONTAINER, OAK_VAULT_CLIENT_FILE",
    ):
        dev(store="vault", vault_url="https://vault.example.test", vault_credential="  ")
    with pytest.raises(ValidationError, match="needs OAK_VAULT_CONTAINER, OAK_VAULT_CLIENT_FILE"):
        dev(store="vault", vault_url="https://vault.example.test", vault_credential="x")
    with pytest.raises(ValidationError, match="needs OAK_VAULT_CLIENT_FILE"):
        dev(
            store="vault",
            vault_url="https://vault.example.test",
            vault_credential="x",
            vault_container="c",
        )
    complete = dev(
        store="vault",
        vault_url="https://vault.example.test",
        vault_credential="x",
        vault_container="c",
        vault_client_file="secrets/client.json",
    )
    assert complete.store == "vault"
    with pytest.raises(ValidationError, match="Input should be 'local' or 'vault'"):
        dev(store="sharepoint")


def test_production_refuses_test_database(dev: MakeSettings) -> None:
    with pytest.raises(ValidationError, match="must name oak_binder when OAK_ENV=production"):
        dev(
            env="production",
            dev_user=None,
            auth="header",
            trusted_proxies="10.0.0.5",
            database_url=BINDER_TEST,
        )
