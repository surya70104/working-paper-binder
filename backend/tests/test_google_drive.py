"""The Google Drive vault adapter against the Drive double (D27): confinement to the vault
folder, write-once with verified uploads, failure mapping, token refresh, and that no secret
ever reaches an error message. No network, no database."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from oak_binder import vault_login
from oak_binder.errors import Conflict, NotFound, StoreUnavailable
from oak_binder.hashing import sha256_of_bytes
from oak_binder.services.attachments import AttachmentStore, verified_read
from oak_binder.services.google_drive import (
    DRIVE_SCOPE,
    GoogleDriveStore,
    OAuthClient,
    TokenFile,
    begin_authorization,
    exchange_code,
    load_client,
)
from tests.fake_drive import ACCESS_TOKEN, CLIENT, FOLDER_ID, REFRESH_TOKEN, FakeDrive

PDF = b"%PDF-1.4 evidence\n"
SECRETS = (ACCESS_TOKEN, REFRESH_TOKEN, CLIENT.client_secret)


def no_secret_in(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text, f"{secret!r} leaked into {text!r}"


@pytest.fixture
def drive() -> FakeDrive:
    return FakeDrive()


# --- the protocol -------------------------------------------------------------------------------


def test_put_files_into_the_vault_folder_marked_and_locked(drive: FakeDrive) -> None:
    store = drive.store()
    assert isinstance(store, AttachmentStore)
    doc_id = store.put(PDF, filename="bank.pdf", media_type="application/pdf")
    stored = drive.files[doc_id]
    assert stored.parents == [FOLDER_ID]
    assert stored.app_properties == {"oak_binder": "attachment", "sha256": sha256_of_bytes(PDF)}
    assert stored.read_only is True  # Drive's content restriction was set
    assert stored.data == PDF and stored.mime_type == "application/pdf"
    assert store.exists(doc_id) and store.read(doc_id) == PDF
    assert doc_id != sha256_of_bytes(PDF)  # an opaque Drive id, not the hash
    # The id/hash separation holds through the Binder's own check.
    assert verified_read(store, _row(doc_id, PDF)) == PDF


def test_the_adapter_never_lists_or_touches_anything_outside_the_folder(drive: FakeDrive) -> None:
    store = drive.store()
    doc_id = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    store.read(doc_id)
    store.exists(doc_id)
    store.exists("drive-does-not-exist")
    store.delete(doc_id)
    assert drive.list_calls() == []
    assert drive.touched_outside_vault() == []
    assert "outside-1" in drive.files  # the personal file is untouched
    assert not any(c.method == "PATCH" and "alt" in c.query for c in drive.calls)


def test_a_file_outside_the_folder_is_not_the_binders_even_when_the_id_is_known(
    drive: FakeDrive,
) -> None:
    store = drive.store()
    assert store.exists("outside-1") is False
    with pytest.raises(NotFound, match="not filed by the Binder"):
        store.read("outside-1")
    with pytest.raises(Conflict, match="refusing to delete"):
        store.delete("outside-1")
    assert "outside-1" in drive.files
    # Only metadata was fetched for it; its bytes were never downloaded.
    assert all(c.query.get("alt") != ["media"] for c in drive.touched_outside_vault())


def test_a_trashed_or_moved_document_counts_as_missing(drive: FakeDrive) -> None:
    store = drive.store()
    doc_id = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    drive.trash(doc_id)
    assert store.exists(doc_id) is False
    with pytest.raises(NotFound, match="trashed, moved"):
        store.read(doc_id)
    other = store.put(PDF + b"2", filename="b.pdf", media_type="application/pdf")
    drive.files[other].parents = ["some-other-folder"]
    assert store.exists(other) is False


def test_altered_bytes_in_drive_are_refused_by_the_verified_read(drive: FakeDrive) -> None:
    store = drive.store()
    doc_id = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    drive.tamper(doc_id, PDF.replace(b"evidence", b"altered!"))
    with pytest.raises(Conflict, match="no longer matches its hash"):
        verified_read(store, _row(doc_id, PDF))


def test_delete_removes_only_vault_documents_and_reports_absence(drive: FakeDrive) -> None:
    store = drive.store()
    doc_id = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    assert store.delete(doc_id) is True
    assert doc_id not in drive.files
    assert store.delete(doc_id) is False
    assert store.delete("drive-never-existed") is False


# --- write-once: an upload that does not verify never stays ---------------------------------------


def test_an_upload_drive_corrupted_is_discarded_and_refused(drive: FakeDrive) -> None:
    store = drive.store()
    drive.corrupt_uploads = True
    with pytest.raises(StoreUnavailable, match="SHA-256 of the upload differs"):
        store.put(PDF, filename="a.pdf", media_type="application/pdf")
    assert drive.vault_files() == {}  # discarded


def test_verification_falls_back_to_md5_then_to_a_read_back(drive: FakeDrive) -> None:
    drive.report_sha256 = False
    store = drive.store()
    doc_id = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    assert drive.files[doc_id].data == PDF
    drive.corrupt_uploads = True
    with pytest.raises(StoreUnavailable, match="MD5 of the upload differs"):
        store.put(PDF + b"x", filename="b.pdf", media_type="application/pdf")
    assert len(drive.vault_files()) == 1


def test_an_upload_that_cannot_be_locked_is_discarded(drive: FakeDrive) -> None:
    store = drive.store()
    drive.refuse_lock = True
    with pytest.raises(StoreUnavailable, match="would not lock"):
        store.put(PDF, filename="a.pdf", media_type="application/pdf")
    assert drive.vault_files() == {}


def test_an_upload_into_a_folder_the_account_cannot_see_fails_clearly() -> None:
    # This is what drive.file would do with a hand-made folder, and what a wrong id does.
    drive = FakeDrive()
    store = GoogleDriveStore("1NotVisibleToThisAccount", drive.store()._tokens, drive.client())
    with pytest.raises(StoreUnavailable, match="did not accept the bytes.*File not found"):
        store.put(PDF, filename="a.pdf", media_type="application/pdf")
    with pytest.raises(StoreUnavailable, match="not visible to this account"):
        store.folder_info()


def test_folder_info_names_the_folder_and_refuses_a_non_folder(drive: FakeDrive) -> None:
    store = drive.store()
    assert store.folder_info() == {
        "id": FOLDER_ID,
        "name": "Working Paper Binder Vault",
        "can_add_children": True,
    }
    drive.files[FOLDER_ID].can_add_children = False
    with pytest.raises(StoreUnavailable, match="may not add files"):
        store.folder_info()
    drive.files[FOLDER_ID].can_add_children = True
    drive.files[FOLDER_ID].trashed = True
    with pytest.raises(StoreUnavailable, match="in the Drive trash"):
        store.folder_info()
    not_folder = FakeDrive(folder_id="outside-1")
    with pytest.raises(StoreUnavailable, match="is not a folder"):
        not_folder.store().folder_info()


# --- tokens and failures -------------------------------------------------------------------------


def test_access_tokens_are_refreshed_once_and_again_after_a_401(drive: FakeDrive) -> None:
    store = drive.store()
    doc_id = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    store.read(doc_id)
    assert drive.token_grants == ["refresh_token"]  # cached in memory across calls
    drive.expire_token()  # Google rotated it: the next call gets a 401, then retries
    assert store.read(doc_id) == PDF
    assert drive.token_grants == ["refresh_token", "refresh_token"]


def test_drive_outages_become_store_unavailable_without_leaking_secrets(drive: FakeDrive) -> None:
    store = drive.store()
    drive.fail_with = 503
    with pytest.raises(StoreUnavailable) as failure:
        store.put(PDF, filename="a.pdf", media_type="application/pdf")
    assert "HTTP 503" in str(failure.value)
    no_secret_in(str(failure.value))
    no_secret_in(repr(store) + repr(store._tokens))

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    offline = GoogleDriveStore(
        FOLDER_ID, drive.store()._tokens, httpx.Client(transport=httpx.MockTransport(unreachable))
    )
    with pytest.raises(StoreUnavailable, match="unreachable") as fault:
        offline.read("drive-x")
    no_secret_in(str(fault.value))


def test_a_revoked_consent_says_to_log_in_again_without_echoing_google(drive: FakeDrive) -> None:
    http = drive.client()
    from oak_binder.services.google_drive import TokenSource

    bad = TokenSource(
        CLIENT,
        TokenFile("stale-refresh", DRIVE_SCOPE, "https://oauth2.googleapis.com/token", ""),
        http,
    )
    with pytest.raises(StoreUnavailable, match="run `python -m oak_binder.vault_login` again") as e:
        bad.access_token()
    assert "invalid_grant" not in str(e.value) and "stale-refresh" not in str(e.value)


# --- credential files -----------------------------------------------------------------------------


def test_client_file_is_parsed_but_never_echoed(tmp_path: Path) -> None:
    path = tmp_path / "client.json"
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "id-123.apps.googleusercontent.com",
                    "client_secret": "GOCSPX-super-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )
    client = load_client(path)
    assert client.client_id == "id-123.apps.googleusercontent.com"
    assert "GOCSPX" not in repr(client)
    (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
    with pytest.raises(StoreUnavailable, match="not a Google 'installed' client JSON") as e:
        load_client(tmp_path / "bad.json")
    assert "GOCSPX" not in str(e.value)
    with pytest.raises(StoreUnavailable, match="not found"):
        load_client(tmp_path / "absent.json")


def test_token_file_round_trips_and_hides_its_content(tmp_path: Path) -> None:
    path = tmp_path / "secrets" / "token.json"
    TokenFile(REFRESH_TOKEN, DRIVE_SCOPE, "https://oauth2.googleapis.com/token", "now").save(path)
    loaded = TokenFile.load(path)
    assert loaded.refresh_token == REFRESH_TOKEN and loaded.scope == DRIVE_SCOPE
    assert REFRESH_TOKEN not in repr(loaded)
    assert not list(path.parent.glob("*.part"))  # written atomically, no leftovers
    with pytest.raises(StoreUnavailable, match="run `python -m oak_binder.vault_login`"):
        TokenFile.load(tmp_path / "missing.json")


def test_from_settings_requires_both_files_and_the_drive_scope(
    tmp_path: Path, drive: FakeDrive
) -> None:
    from tests.conftest import IsolatedSettings

    client_file = tmp_path / "client.json"
    client_file.write_text(
        json.dumps({"installed": {"client_id": CLIENT.client_id, "client_secret": "s"}}),
        encoding="utf-8",
    )
    token_file = tmp_path / "token.json"

    def settings(**extra: Any) -> Any:
        base: dict[str, Any] = {
            "env": "test",
            "database_url": "postgresql+psycopg://oak_binder_app:x@localhost:5432/oak_binder",
            "store": "vault",
            "vault_url": "https://www.googleapis.com/drive/v3",
            "vault_container": FOLDER_ID,
            "vault_credential": str(token_file),
            "vault_client_file": str(client_file),
        }
        base.update(extra)
        return IsolatedSettings(**base)

    with pytest.raises(StoreUnavailable, match="token file not found"):
        GoogleDriveStore.from_settings(settings(), drive.client())
    TokenFile(REFRESH_TOKEN, "https://www.googleapis.com/auth/drive.file", "", "").save(token_file)
    with pytest.raises(StoreUnavailable, match="was not granted the drive scope"):
        GoogleDriveStore.from_settings(settings(), drive.client())
    TokenFile(REFRESH_TOKEN, DRIVE_SCOPE, "", "").save(token_file)
    store = GoogleDriveStore.from_settings(settings(), drive.client())
    assert store.folder_id == FOLDER_ID
    assert store.folder_info()["name"] == "Working Paper Binder Vault"


# --- the one-time consent -------------------------------------------------------------------


def test_consent_url_asks_for_offline_drive_access_with_pkce() -> None:
    pending = begin_authorization(CLIENT, "http://127.0.0.1:4321/")
    assert pending.url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    for needle in (
        "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive",
        "access_type=offline",
        "prompt=consent",
        "code_challenge_method=S256",
        f"state={pending.state}",
        "redirect_uri=http%3A%2F%2F127.0.0.1%3A4321%2F",
    ):
        assert needle in pending.url, needle
    assert CLIENT.client_secret not in pending.url
    assert pending.verifier not in pending.url  # only its hash travels


def test_code_exchange_yields_a_refresh_token_and_never_echoes_a_refusal(drive: FakeDrive) -> None:
    pending = begin_authorization(CLIENT, "http://127.0.0.1:4321/")
    tokens = exchange_code(drive.client(), CLIENT, pending, "good-code")
    assert tokens.refresh_token == REFRESH_TOKEN and DRIVE_SCOPE in tokens.scope
    with pytest.raises(StoreUnavailable, match="refused the authorization code") as e:
        exchange_code(drive.client(), CLIENT, pending, "bad-code")
    assert "invalid_grant" not in str(e.value)


def test_loopback_server_accepts_one_matching_redirect_and_refuses_a_wrong_state() -> None:
    pending = begin_authorization(CLIENT, "http://127.0.0.1:0/")
    server = vault_login._CodeCatcher(("127.0.0.1", 0), vault_login._Handler)
    port = server.server_address[1]
    result: dict[str, str] = {}

    def browser() -> None:
        with httpx.Client() as http:
            result["body"] = http.get(
                f"http://127.0.0.1:{port}/", params={"code": "good-code", "state": pending.state}
            ).text

    thread = threading.Thread(target=browser)
    thread.start()
    code = vault_login.wait_for_code(server, pending, timeout=10)
    thread.join()
    server.server_close()
    assert code == "good-code" and "consent received" in result["body"]

    server = vault_login._CodeCatcher(("127.0.0.1", 0), vault_login._Handler)
    port = server.server_address[1]
    thread = threading.Thread(
        target=lambda: httpx.get(
            f"http://127.0.0.1:{port}/", params={"code": "good-code", "state": "forged"}
        )
    )
    thread.start()
    with pytest.raises(StoreUnavailable, match="expected state"):
        vault_login.wait_for_code(server, pending, timeout=10)
    thread.join()
    server.server_close()


def test_login_end_to_end_against_the_double_saves_the_token_and_checks_the_folder(
    tmp_path: Path, drive: FakeDrive, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import IsolatedSettings

    client_file = tmp_path / "client.json"
    client_file.write_text(
        json.dumps(
            {"installed": {"client_id": CLIENT.client_id, "client_secret": CLIENT.client_secret}}
        ),
        encoding="utf-8",
    )
    token_file = tmp_path / "secrets" / "token.json"
    settings = IsolatedSettings(
        env="test",
        database_url="postgresql+psycopg://oak_binder_app:x@localhost:5432/oak_binder",
        store="local",  # the consent is done before vault mode is switched on
        vault_url="https://www.googleapis.com/drive/v3",
        vault_container=FOLDER_ID,
        vault_credential=str(token_file),
        vault_client_file=str(client_file),
    )

    # Stand in for the person: follow the consent URL's redirect_uri with a good code.
    def fake_browser(url: str) -> bool:
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(url).query)
        redirect = query["redirect_uri"][0]
        httpx.get(redirect, params={"code": "good-code", "state": query["state"][0]})
        return True

    import webbrowser

    monkeypatch.setattr(webbrowser, "open", fake_browser)
    import io

    out = io.StringIO()
    name = vault_login.login(settings, drive.client(), open_browser=True, timeout=10, out=out)
    assert name == "Working Paper Binder Vault"
    assert TokenFile.load(token_file).refresh_token == REFRESH_TOKEN
    printed = out.getvalue()
    no_secret_in(printed)
    assert "good-code" not in printed
    assert drive.token_grants[0] == "authorization_code"


def _row(doc_id: str, data: bytes) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(vault_doc_id=doc_id, sha256=sha256_of_bytes(data))


def test_oauth_client_dataclass_never_prints_its_secret() -> None:
    client = OAuthClient("id", "very-secret")  # noqa: S106
    assert "very-secret" not in repr(client) and "very-secret" not in str(client)
