"""One-time consent for the Google Drive vault (D27).

    python -m oak_binder.vault_login            consent in the browser, save the token, check
    python -m oak_binder.vault_login --check    only check the saved token against the folder
    python -m oak_binder.vault_login --no-browser   print the consent URL instead of opening it

Reads OAK_VAULT_CLIENT_FILE (the Desktop OAuth client JSON) and writes OAK_VAULT_CREDENTIAL
(the refresh token), both under the git-ignored backend/secrets directory. Prints the vault
folder's name and nothing from either file. Works whatever OAK_STORE is set to, so the
consent can be done and checked before vault mode is switched on.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TextIO
from urllib.parse import parse_qs, urlparse

import httpx

from oak_binder.config import Settings, get_settings
from oak_binder.errors import StoreUnavailable
from oak_binder.services.google_drive import (
    TIMEOUT,
    GoogleDriveStore,
    PendingAuthorization,
    begin_authorization,
    exchange_code,
    load_client,
)

LOOPBACK = "127.0.0.1"


class _CodeCatcher(HTTPServer):
    """A loopback server that accepts exactly one redirect from Google."""

    code: str | None = None
    state: str | None = None
    error: str | None = None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002  (stdlib name)
        return  # never log the request line: it carries the code

    def do_GET(self) -> None:  # noqa: N802  (stdlib name)
        server = self.server
        assert isinstance(server, _CodeCatcher)  # noqa: S101
        query = parse_qs(urlparse(self.path).query)

        def first(name: str) -> str | None:
            values = query.get(name)
            return values[0] if values else None

        server.code = first("code")
        server.state = first("state")
        server.error = first("error")
        body = (
            b"Working Paper Binder: consent received. You can close this window."
            if server.code
            else b"Working Paper Binder: consent was not granted. You can close this window."
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def wait_for_code(server: _CodeCatcher, pending: PendingAuthorization, timeout: float) -> str:
    """Serve one request, then return the code if the state matches."""
    server.timeout = timeout
    server.handle_request()
    if server.error:
        raise StoreUnavailable(f"Google reported {server.error!r}; no token was saved")
    if not server.code:
        raise StoreUnavailable("no authorization code arrived before the timeout")
    if server.state != pending.state:
        raise StoreUnavailable("the redirect did not carry the expected state; refused")
    return server.code


def _paths(settings: Settings) -> tuple[Path, Path]:
    if not settings.vault_client_file or not settings.vault_credential:
        raise StoreUnavailable(
            "set OAK_VAULT_CLIENT_FILE (the Desktop client JSON) and OAK_VAULT_CREDENTIAL "
            "(where to keep the refresh token) in backend/.env first (D27)"
        )
    return Path(settings.vault_client_file), Path(settings.vault_credential)


def check(settings: Settings, http: httpx.Client) -> str:
    """Verify the saved token reaches the vault folder. Returns the folder's name."""
    store = GoogleDriveStore.from_settings(settings, http)
    info = store.folder_info()
    return str(info["name"])


def login(
    settings: Settings,
    http: httpx.Client,
    *,
    open_browser: bool,
    timeout: float = 300.0,
    out: TextIO | None = None,
) -> str:
    """Run the consent, save the token file, check the folder. Returns the folder's name."""
    client_path, token_path = _paths(settings)
    client = load_client(client_path)
    server = _CodeCatcher((LOOPBACK, 0), _Handler)
    redirect_uri = f"http://{LOOPBACK}:{server.server_address[1]}/"
    pending = begin_authorization(client, redirect_uri)
    stream: TextIO = out if out is not None else sys.stdout
    if open_browser:
        print("Opening the Google consent page in your browser…", file=stream)  # noqa: T201
        threading.Thread(target=webbrowser.open, args=(pending.url,), daemon=True).start()
    else:
        print("Open this URL in a browser signed in to the vault account:", file=stream)  # noqa: T201
        print(pending.url, file=stream)  # noqa: T201
    print(  # noqa: T201
        f"Waiting up to {int(timeout)} s for the consent redirect on {redirect_uri} …",
        file=stream,
    )
    try:
        code = wait_for_code(server, pending, timeout)
    finally:
        server.server_close()
    tokens = exchange_code(http, client, pending, code)
    tokens.save(token_path)
    print(f"Refresh token saved to {token_path} (not shown).", file=stream)  # noqa: T201
    return check(settings, http)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-time Google Drive consent for the vault")
    parser.add_argument("--check", action="store_true", help="only verify the saved token")
    parser.add_argument("--no-browser", action="store_true", help="print the URL instead")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        with httpx.Client(timeout=TIMEOUT) as http:
            if args.check:
                name = check(settings, http)
            else:
                name = login(settings, http, open_browser=not args.no_browser)
    except StoreUnavailable as exc:
        print(f"FAILED: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    print(f"OK: the vault folder {name!r} is reachable and accepts files.")  # noqa: T201
    print(  # noqa: T201
        "OAK_STORE is still "
        f"{settings.store!r}; switch it to 'vault' only after the migration and tests pass."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
