"""Shared fixtures.

Tests never read backend/.env or the OAK_* environment variables for settings:
``IsolatedSettings`` keeps only the values a test passes in, so a developer's real
configuration cannot leak into a test.

Database tests (marked ``db``) are the exception: they need OAK_TEST_DATABASE_URL, and
optionally OAK_TEST_APP_DATABASE_URL. ``TestDatabaseUrls`` reads those two names, and only
those, from the shell environment first and then from backend/.env. Both must name
oak_binder_test, checked by the same guard the application uses. Without them the tests are
skipped, never silently passed.

The test database is shared with browser demos, so the suite preserves what it finds: the
schema is only ever upgraded, every test runs in a transaction that is rolled back, and every
engagement name a test creates carries a random suffix (``unique``). Destroying and
rebuilding the database requires OAK_TEST_REBUILD=yes.
"""

from __future__ import annotations

import io
import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from sqlalchemy import Connection
from sqlalchemy.orm import sessionmaker

from oak_binder.config import TEST_DATABASE, Settings, check_binder_url
from oak_binder.db import make_engine
from oak_binder.main import create_app
from oak_binder.services.attachments import InMemoryVaultStore
from tests.fake_spine import FakeSpine
from tests.fake_workmind import FakeWorkMind

APP_URL = "postgresql+psycopg://oak_binder_app:placeholder@localhost:5432/oak_binder"
TEST_URL = "postgresql+psycopg://oak_binder_owner:placeholder@localhost:5432/oak_binder_test"

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


class IsolatedSettings(Settings):
    """Settings whose only source is the constructor: no .env, no environment variables."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


class TestDatabaseUrls(BaseSettings):
    """The two test connection strings. Environment variables win over backend/.env, as in
    pydantic-settings generally. Nothing else from .env is read here."""

    __test__ = False  # not a test class, despite the name

    model_config = SettingsConfigDict(
        env_prefix="OAK_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    test_database_url: str | None = None
    test_app_database_url: str | None = None


def test_url(variable: str) -> str | None:
    """The validated URL for OAK_TEST_DATABASE_URL or OAK_TEST_APP_DATABASE_URL, or None."""
    field = variable.removeprefix("OAK_").lower()
    url = getattr(TestDatabaseUrls(), field)
    if not url:
        return None
    return check_binder_url(url, allowed=frozenset({TEST_DATABASE}), name=variable)


def alembic_config(url: str, *, output: io.StringIO | None = None) -> Config:
    """Alembic configuration driven from code: the URL goes through env.py's guard."""
    cfg = Config(str(ALEMBIC_INI), output_buffer=output)
    cfg.attributes["migration_url"] = url
    cfg.attributes["skip_logging_config"] = True
    return cfg


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if test_url("OAK_TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="OAK_TEST_DATABASE_URL is not set; database tests skipped")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    """Build Settings from explicit values only. Validation runs exactly as in production."""

    def _make(**values: Any) -> Settings:
        return IsolatedSettings(**values)

    return _make


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(
        env="test",
        database_url=APP_URL,
        migration_database_url=TEST_URL,
        dev_user="test@localhost",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


# --- database fixtures: only when OAK_TEST_DATABASE_URL is set -------------------------------


def _url_from_env(variable: str) -> str:
    url = test_url(variable)
    if not url:
        pytest.skip(f"{variable} is not set; database tests skipped")
    return url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Owner connection to oak_binder_test: migrates and inserts."""
    return _url_from_env("OAK_TEST_DATABASE_URL")


REBUILD_FLAG = "OAK_TEST_REBUILD"


def rebuild_allowed() -> bool:
    """True only when the developer has opted in to destroying oak_binder_test's contents."""
    return os.environ.get(REBUILD_FLAG, "").lower() in {"yes", "1", "true"}


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> str:
    """oak_binder_test at migration head. Existing rows are preserved: only ``upgrade head``
    runs, which applies any migration not yet applied and is otherwise a no-op. A full
    rebuild (downgrade to nothing first) happens only with OAK_TEST_REBUILD=yes."""
    cfg = alembic_config(test_database_url)
    if rebuild_allowed():
        command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return test_database_url


def unique(label: str) -> str:
    """An engagement name that cannot collide with rows already in the test database."""
    return f"{label}-{uuid.uuid4().hex[:8]}"


def _rolled_back_connection(url: str) -> Iterator[Connection]:
    engine = make_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.fixture
def db(migrated_database: str) -> Iterator[Connection]:
    """Owner connection inside a transaction that is rolled back after the test."""
    yield from _rolled_back_connection(migrated_database)


@pytest.fixture
def app_db(migrated_database: str) -> Iterator[Connection]:
    """Application-role connection (oak_binder_app), rolled back after the test."""
    yield from _rolled_back_connection(_url_from_env("OAK_TEST_APP_DATABASE_URL"))


PREPARER = "preparer@firm"
REVIEWER = "reviewer@firm"


@pytest.fixture
def api(
    migrated_database: str, make_settings: Callable[..., Settings], tmp_path: Path
) -> Iterator[TestClient]:
    """The whole API against oak_binder_test, as the application role when its URL is set.

    Every request's session is bound to one connection inside one transaction; commits
    become savepoint releases and the transaction is rolled back after the test, so the
    database is left exactly as the migration made it. Attachments go to a temporary
    directory, never to var\\attachments, and the upload limit is small so a test can
    exceed it cheaply.
    """
    url = test_url("OAK_TEST_APP_DATABASE_URL") or migrated_database
    settings = make_settings(
        env="test",
        database_url=url,
        dev_user=PREPARER,
        attachments_dir=tmp_path / "attachments",
        max_upload_bytes=64 * 1024,
    )
    app = create_app(settings)
    engine = make_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        app.state.session_factory = sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            with TestClient(app) as client:
                yield client
        finally:
            transaction.rollback()
    engine.dispose()
    app.state.engine.dispose()


def act_as(api: TestClient, user: str | None) -> None:
    """Change the development identity the API records as preparer or reviewer."""
    cast(FastAPI, api.app).state.settings.dev_user = user


def use_spine(api: TestClient) -> FakeSpine:
    """Give the running app a Financial Spine double (D29)."""
    spine = FakeSpine()
    cast(FastAPI, api.app).state.spine_client = spine.client()
    return spine


def use_workmind(api: TestClient, credential: str | None = None) -> FakeWorkMind:
    """Give the running app a WorkMind double (D37)."""
    workmind = FakeWorkMind()
    cast(FastAPI, api.app).state.workmind_client = workmind.client(credential)
    return workmind


def use_vault(api: TestClient) -> InMemoryVaultStore:
    """Swap the running app's store for the in-memory vault stand-in (D23)."""
    store = InMemoryVaultStore()
    cast(FastAPI, api.app).state.attachment_store = store
    return store
