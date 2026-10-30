"""Identity sources (spec 7; D8, D24): the development identity, the proxy header, and what
production allows. No database: the health check and a bare app are enough."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from oak_binder.config import Settings
from oak_binder.identity import current_user, identity_from

MakeSettings = Callable[..., Settings]
URL = "postgresql+psycopg://oak_binder_app:x@localhost:5432/oak_binder"


def app_with(settings: Settings, client: tuple[str, int] = ("testclient", 50000)) -> TestClient:
    app = FastAPI()
    app.state.settings = settings

    @app.get("/whoami")
    def whoami(user: str = __import__("fastapi").Depends(current_user)) -> dict[str, str]:
        return {"user": user}

    return TestClient(app, client=client)


def test_dev_identity_comes_from_settings(make_settings: MakeSettings) -> None:
    client = app_with(make_settings(env="test", database_url=URL, dev_user="dev@localhost"))
    assert client.get("/whoami").json() == {"user": "dev@localhost"}
    # A client-sent header is ignored in dev mode.
    assert client.get("/whoami", headers={"X-Authenticated-User": "x"}).json() == {
        "user": "dev@localhost"
    }


def test_dev_mode_without_an_identity_refuses_with_503(make_settings: MakeSettings) -> None:
    client = app_with(make_settings(env="test", database_url=URL, dev_user=None))
    response = client.get("/whoami")
    assert response.status_code == 503
    assert "No identity is configured" in response.json()["detail"]


def test_header_mode_takes_the_identity_from_the_proxy_header(
    make_settings: MakeSettings,
) -> None:
    settings = make_settings(env="test", database_url=URL, auth="header", dev_user=None)
    client = app_with(settings)
    ok = client.get("/whoami", headers={"X-Authenticated-User": "  partner@firm "})
    assert ok.json() == {"user": "partner@firm"}  # case-insensitive header, trimmed
    none = client.get("/whoami")
    assert none.status_code == 401
    assert "did not present X-Authenticated-User" in none.json()["detail"]
    blank = client.get("/whoami", headers={"X-Authenticated-User": "   "})
    assert blank.status_code == 401
    # dev_user is never a fallback in header mode
    settings.dev_user = "dev@localhost"
    assert client.get("/whoami").status_code == 401


def test_header_name_is_configurable(make_settings: MakeSettings) -> None:
    settings = make_settings(env="test", database_url=URL, auth="header", auth_header="Remote-User")
    assert identity_from(settings, {"remote-user": "a@firm"}) == "a@firm"
    assert identity_from(settings, {"x-authenticated-user": "a@firm"}) is None


def test_production_refuses_the_development_identity_source(make_settings: MakeSettings) -> None:
    with pytest.raises(
        ValidationError, match="OAK_AUTH=dev is not allowed when OAK_ENV=production"
    ):
        make_settings(env="production", database_url=URL, dev_user=None)
    # Header mode in production also needs the proxy's address, or anyone who reaches the
    # API could name themselves.
    with pytest.raises(ValidationError, match="OAK_TRUSTED_PROXIES must list"):
        make_settings(env="production", database_url=URL, dev_user=None, auth="header")
    ok = make_settings(
        env="production",
        database_url=URL,
        dev_user=None,
        auth="header",
        trusted_proxies="10.0.0.5, 192.168.1.0/24",
    )
    assert ok.auth == "header" and len(ok.trusted_networks()) == 2


def test_trusted_proxies_must_be_addresses(make_settings: MakeSettings) -> None:
    with pytest.raises(ValidationError, match="OAK_TRUSTED_PROXIES must be a comma-separated"):
        make_settings(env="test", database_url=URL, auth="header", trusted_proxies="proxy.local")


def test_header_is_believed_only_from_a_trusted_proxy(make_settings: MakeSettings) -> None:
    settings = make_settings(
        env="test", database_url=URL, auth="header", trusted_proxies="10.0.0.5, 10.1.0.0/16"
    )
    headers = {"X-Authenticated-User": "partner@firm"}
    stranger = app_with(settings, client=("203.0.113.9", 4000)).get("/whoami", headers=headers)
    assert stranger.status_code == 401
    assert "did not arrive through a trusted proxy" in stranger.json()["detail"]
    for host in ("10.0.0.5", "10.1.200.7"):
        ok = app_with(settings, client=(host, 4000)).get("/whoami", headers=headers)
        assert ok.status_code == 200 and ok.json() == {"user": "partner@firm"}, host
    # Without a list (development), any peer is accepted; the production guard forbids that.
    open_settings = make_settings(env="test", database_url=URL, auth="header")
    assert app_with(open_settings).get("/whoami", headers=headers).status_code == 200


def test_header_mode_refuses_a_repeated_or_implausible_header(
    make_settings: MakeSettings,
) -> None:
    client = app_with(make_settings(env="test", database_url=URL, auth="header"))
    # A proxy that appends instead of replacing would leave a client-sent copy in front.
    twice = client.get(
        "/whoami",
        headers=[("X-Authenticated-User", "attacker"), ("X-Authenticated-User", "partner@firm")],
    )
    assert twice.status_code == 401 and "presented 2 times" in twice.json()["detail"]
    for bad in ("a" * 255, "partner@firm\x7f", "two\twords"):
        response = client.get("/whoami", headers={"X-Authenticated-User": bad})
        assert response.status_code == 401, bad
        assert "usable identity" in response.json()["detail"]
    assert client.get("/whoami", headers={"X-Authenticated-User": "a" * 254}).status_code == 200


def test_header_mode_needs_a_header_name(make_settings: MakeSettings) -> None:
    with pytest.raises(ValidationError, match="OAK_AUTH=header needs OAK_AUTH_HEADER"):
        make_settings(env="test", database_url=URL, auth="header", auth_header="  ")
