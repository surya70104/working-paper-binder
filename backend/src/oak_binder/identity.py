"""Who is acting (spec 7, architecture D8, D24).

One mechanism, two sources, chosen by OAK_AUTH:

- ``dev``: the fixed identity in OAK_DEV_USER. For development and tests; refused in
  production by the settings guard.
- ``header``: the identity an authenticating reverse proxy places in the configured header
  after signing the user in (the identity-aware-proxy pattern). The Binder trusts the header
  and verifies nothing about the person itself. What it does check, because a header is only
  as trustworthy as its route in:

  * the request reached the API from a trusted proxy address (OAK_TRUSTED_PROXIES, a list
    of IPs or networks; required in production), so a client that can reach the API
    directly cannot name itself;
  * the header appears exactly once, so a proxy that appends rather than replaces cannot
    leave a client-sent copy in front of its own;
  * the value is a plausible name: non-blank, at most 254 characters, no control characters.

  Which proxy or identity provider the firm uses is its decision; nothing here depends on it.

Every action that records a person (sign-offs, notes, attachments, assembly, production,
purge, and reads of an assembled file) depends on ``current_user``, so without an identity
those actions refuse rather than record an empty name. ``optional_user`` is for the one
place an identity is welcome but not required: a read of an open binder.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from oak_binder.config import Settings

MAX_IDENTITY_LENGTH = 254


def identity_from(settings: Settings, headers: dict[str, str] | None) -> str | None:
    """The acting identity from a lower-cased header map, or None when the configured source
    offers none. The route and duplicate checks live in ``resolve``; this is the value."""
    if settings.auth == "header":
        value = (headers or {}).get(settings.auth_header.lower(), "")
        return value.strip() or None
    return (settings.dev_user or "").strip() or None


def plausible(value: str) -> bool:
    """A name a person or identity provider would present: printable, bounded."""
    return 0 < len(value) <= MAX_IDENTITY_LENGTH and not any(
        ch.isspace() and ch != " " or ord(ch) < 32 or ord(ch) == 127 for ch in value
    )


def from_trusted_proxy(settings: Settings, client_host: str | None) -> bool:
    """True when no proxy list is configured (development) or the immediate client address
    is in it. The address is the socket peer, never a forwarded header, so run the server
    without proxy-header rewriting: the proxy must be the peer."""
    networks = settings.trusted_networks()
    if not networks:
        return True
    if not client_host:
        return False
    try:
        address = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    return any(address in network for network in networks)


@dataclass(frozen=True)
class Resolution:
    user: str | None
    status_code: int
    detail: str


def resolve(request: Request) -> Resolution:
    """The identity for this request, or why there is none and which status says so."""
    settings: Settings = request.app.state.settings
    if settings.auth == "header":
        name = settings.auth_header
        client_host = request.client.host if request.client else None
        if not from_trusted_proxy(settings, client_host):
            return Resolution(
                None,
                status.HTTP_401_UNAUTHORIZED,
                "Request did not arrive through a trusted proxy, so its identity header "
                "cannot be believed (OAK_TRUSTED_PROXIES; architecture D24).",
            )
        values = request.headers.getlist(name)
        if len(values) > 1:
            return Resolution(
                None,
                status.HTTP_401_UNAUTHORIZED,
                f"{name} was presented {len(values)} times; the proxy must replace, not "
                "append, the header (architecture D24).",
            )
        value = values[0].strip() if values else ""
        if not value:
            return Resolution(
                None,
                status.HTTP_401_UNAUTHORIZED,
                f"No authenticated identity: the proxy did not present {name} (architecture D24).",
            )
        if not plausible(value):
            return Resolution(
                None,
                status.HTTP_401_UNAUTHORIZED,
                f"{name} does not hold a usable identity (blank, too long or not printable).",
            )
        return Resolution(value, status.HTTP_200_OK, "")
    user = (settings.dev_user or "").strip() or None
    if user:
        return Resolution(user, status.HTTP_200_OK, "")
    return Resolution(
        None,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "No identity is configured: set OAK_DEV_USER for development, "
        "or OAK_AUTH=header behind an authenticating proxy (architecture D8, D24).",
    )


def current_user(request: Request) -> str:
    found = resolve(request)
    if found.user is None:
        raise HTTPException(found.status_code, found.detail)
    return found.user


def optional_user(request: Request) -> str | None:
    """The identity if one is validly present; None otherwise, never an error."""
    return resolve(request).user
