"""The read-only Spine client against the Spine double (D29): paths and verbs, the records
it returns, error mapping, the optional bearer credential and its redaction, and the
settings that configure it. No network, no database."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from oak_binder.config import Settings, spine_url_is_secure
from oak_binder.errors import Invalid, NotFound, SpineUnavailable
from oak_binder.services.spine_client import build_spine_client
from tests.fake_spine import (
    ENGAGEMENT_ID,
    LOCKED_HASH,
    LOCKED_VERSION_ID,
    OPEN_VERSION_ID,
    OTHER_VERSION_ID,
    TOKEN,
    FakeSpine,
)

URL = "postgresql+psycopg://oak_binder_app:x@localhost:5432/oak_binder"


@pytest.fixture
def spine() -> FakeSpine:
    return FakeSpine()


def test_every_call_is_a_get_on_the_documented_path(spine: FakeSpine) -> None:
    client = spine.client()
    assert client.health()["status"] == "ok"
    engagement = client.engagement(ENGAGEMENT_ID)
    assert engagement.label == "FY 2025-26 statutory audit"
    assert str(engagement.financial_year_end) == "2026-03-31"
    versions = client.versions(ENGAGEMENT_ID)
    assert [v.version_no for v in versions] == [2, 1]  # newest first, as the Spine serves
    locked = client.version(LOCKED_VERSION_ID)
    assert locked.is_locked and locked.hash == LOCKED_HASH and locked.locked_at is not None
    assert locked.adjustments == {"proposed": 0, "accepted": 2, "refused": 1}
    assert locked.performance_materiality == "250000.00"
    unlocked = client.version(OPEN_VERSION_ID)
    assert not unlocked.is_locked and unlocked.hash is None
    presentation = client.presentation(LOCKED_VERSION_ID)
    assert presentation.is_locked and not presentation.provisional
    # Only lines with a stable head_id are financial-statement lines; subtotals are left out.
    assert [line.head_id for line in presentation.lines] == ["BS.A.1", "BS.L.1", "PL.R.1"]
    assert presentation.lines[0].label == "Cash and cash equivalents"
    assert client.balances(LOCKED_VERSION_ID)["hash"] == LOCKED_HASH
    assert [a["status"] for a in client.adjustments(LOCKED_VERSION_ID)] == [
        "accepted",
        "proposed",
        "refused",
    ]
    assert client.uncorrected(LOCKED_VERSION_ID)["aggregate"] == "15000.00"
    assert spine.non_get_calls() == []
    assert [c.path for c in spine.calls][:3] == [
        "/api/health",
        f"/api/engagements/{ENGAGEMENT_ID}",
        f"/api/engagements/{ENGAGEMENT_ID}/spine-versions",
    ]
    assert all(c.headers.get("accept") == "application/json" for c in spine.calls)
    assert all("authorization" not in c.headers for c in spine.calls)


def test_errors_are_mapped_once_and_carry_the_spines_message(spine: FakeSpine) -> None:
    client = spine.client()
    with pytest.raises(NotFound, match="No engagement .* exists"):
        client.engagement(uuid.uuid4())
    with pytest.raises(NotFound, match="No spine_version .* exists"):
        client.version(uuid.uuid4())
    spine.fail_with = 503
    with pytest.raises(SpineUnavailable, match="could not answer .*HTTP 503.*database could not"):
        client.version(LOCKED_VERSION_ID)
    spine.fail_with = 422
    with pytest.raises(Invalid, match="the Financial Spine refused"):
        client.version(LOCKED_VERSION_ID)
    spine.fail_with = None
    spine.non_json = True
    with pytest.raises(SpineUnavailable, match="unexpected answer"):
        client.version(LOCKED_VERSION_ID)
    spine.non_json = False
    spine.time_out = True
    with pytest.raises(SpineUnavailable, match="did not answer in time"):
        client.version(LOCKED_VERSION_ID)


def test_the_bearer_credential_is_sent_when_set_and_never_shown(spine: FakeSpine) -> None:
    spine.require_token = True
    with pytest.raises(SpineUnavailable, match="refused the Binder's credential") as refused:
        spine.client().version(LOCKED_VERSION_ID)
    assert TOKEN not in str(refused.value)
    with_token = spine.client(credential=f" {TOKEN} ")
    assert with_token.version(LOCKED_VERSION_ID).is_locked
    assert spine.calls[-1].headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in repr(with_token)
    assert "credential=set" in repr(with_token)
    assert "credential=none" in repr(spine.client())


def test_a_version_of_another_engagement_is_reported_as_such(spine: FakeSpine) -> None:
    other = spine.client().version(OTHER_VERSION_ID)
    assert other.engagement_id != ENGAGEMENT_ID


def test_settings_configure_or_omit_the_spine(make_settings: Callable[..., Settings]) -> None:
    none = make_settings(env="test", database_url=URL)
    assert none.spine_url is None and build_spine_client(none) is None
    some = make_settings(env="test", database_url=URL, spine_url="http://127.0.0.1:8000/")
    assert some.spine_url == "http://127.0.0.1:8000"
    client = build_spine_client(some)
    assert client is not None and client.base_url == "http://127.0.0.1:8000"
    for bad in ("127.0.0.1:8000", "ftp://spine", "http://", "   "):
        if bad.strip() == "":
            assert make_settings(env="test", database_url=URL, spine_url=bad).spine_url is None
            continue
        with pytest.raises(ValidationError, match="OAK_SPINE_URL must be an http"):
            make_settings(env="test", database_url=URL, spine_url=bad)


def test_production_needs_https_unless_loopback(make_settings: Callable[..., Settings]) -> None:
    production: dict[str, Any] = dict(
        env="production", database_url=URL, dev_user=None, auth="header", trusted_proxies="10.0.0.5"
    )
    assert make_settings(**production, spine_url="http://127.0.0.1:8000").spine_url
    assert make_settings(**production, spine_url="http://localhost:8000").spine_url
    assert make_settings(**production, spine_url="https://spine.firm.example").spine_url
    with pytest.raises(ValidationError, match="must use https"):
        make_settings(**production, spine_url="http://spine.firm.example:8000")
    assert spine_url_is_secure("http://[::1]:8000") and not spine_url_is_secure("http://10.0.0.9")
