"""Google Drive as the attachment vault (spec 6 "attachments from the vault"; D7, D23, D27).

``GoogleDriveStore`` implements the ``AttachmentStore`` protocol against the Drive REST API
(v3) for one folder the firm created by hand. The document id is Drive's file id, opaque to
the Binder; the Binder's own SHA-256 stays on every row and every read is re-hashed by
``verified_read`` as for any store.

What the adapter guarantees, and how:

- **Confinement to the vault folder.** The OAuth scope Google requires for a folder a person
  created is the full ``drive`` scope, which technically reaches the whole account. The
  adapter therefore confines itself: every file it creates has the vault folder as its only
  parent and carries an application marker; every read, existence check and delete first
  fetches the file's metadata and refuses a file that is not in the folder, is not marked, or
  is in the trash. It never lists, searches, updates or deletes anything else, and the test
  double asserts no list call is ever made.
- **Write-once.** Bytes are uploaded once, verified against the hash Drive reports (SHA-256
  when Drive returns it, otherwise MD5, otherwise a read-back), and the file is then given
  Drive's read-only content restriction. Nothing here ever calls the update-content endpoint.
  Drive's restriction is a soft lock: a person with edit rights can lift it, which is why the
  hash check on every read remains the real integrity rule.
- **Secrets.** The OAuth client file and the refresh-token file live under the git-ignored
  ``backend/secrets`` directory and are read into memory only. Their contents never appear in
  logs, errors or responses: errors carry status codes and Drive's own message for file
  endpoints, and nothing at all from the token endpoint.
- **Failure.** A network fault, a quota refusal or a 5xx becomes ``StoreUnavailable`` (503),
  so an upload or production fails clearly rather than half-writing.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from oak_binder.config import Settings
from oak_binder.errors import Conflict, Invalid, NotFound, StoreUnavailable
from oak_binder.hashing import sha256_of_bytes

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
API_BASE = "https://www.googleapis.com/drive/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105  (an endpoint, not a secret)
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
FOLDER_MIME = "application/vnd.google-apps.folder"

MARKER_KEY = "oak_binder"
MARKER_VALUE = "attachment"
METADATA_FIELDS = (
    "id,name,mimeType,parents,trashed,size,md5Checksum,sha256Checksum,appProperties,"
    "contentRestrictions"
)
FOLDER_FIELDS = "id,name,mimeType,trashed,capabilities(canAddChildren)"
TIMEOUT = httpx.Timeout(60.0, connect=15.0)


# --- credentials -------------------------------------------------------------------------------


@dataclass(frozen=True)
class OAuthClient:
    """The Desktop OAuth client Google issued. Loaded from the client JSON; never printed."""

    client_id: str
    client_secret: str
    auth_uri: str = AUTH_URI
    token_uri: str = TOKEN_URI

    def __repr__(self) -> str:  # never leak the secret through a traceback or log
        return "OAuthClient(<redacted>)"


def load_client(path: Path) -> OAuthClient:
    if not path.is_file():
        raise StoreUnavailable(f"OAuth client file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        block = raw.get("installed") or raw.get("web")
        return OAuthClient(
            client_id=str(block["client_id"]),
            client_secret=str(block["client_secret"]),
            auth_uri=str(block.get("auth_uri") or AUTH_URI),
            token_uri=str(block.get("token_uri") or TOKEN_URI),
        )
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        # Say what is wrong with the file's shape, never what is in it.
        raise StoreUnavailable(
            f"OAuth client file {path.name} is not a Google 'installed' client JSON"
        ) from exc


@dataclass
class TokenFile:
    """The refresh token obtained by the one-time consent (vault_login) and the scope it was
    granted for. Written with owner-only permissions where the OS supports it."""

    refresh_token: str
    scope: str
    token_uri: str
    obtained_at: str

    def __repr__(self) -> str:
        return "TokenFile(<redacted>)"

    @classmethod
    def load(cls, path: Path) -> TokenFile:
        if not path.is_file():
            raise StoreUnavailable(
                f"Drive token file not found: {path}; run `python -m oak_binder.vault_login`"
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                refresh_token=str(raw["refresh_token"]),
                scope=str(raw.get("scope", "")),
                token_uri=str(raw.get("token_uri") or TOKEN_URI),
                obtained_at=str(raw.get("obtained_at", "")),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise StoreUnavailable(f"Drive token file {path.name} is not usable") from exc

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            {
                "refresh_token": self.refresh_token,
                "scope": self.scope,
                "token_uri": self.token_uri,
                "obtained_at": self.obtained_at,
            },
            indent=2,
        )
        temp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.part")
        temp.write_text(body, encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass  # Windows: rely on the directory's ACL and the ignore rule
        os.replace(temp, path)


class StoreError(StoreUnavailable):
    """A Drive call failed. The message names the operation and status, never a token."""


def _drive_message(response: httpx.Response) -> str:
    """Drive's own error message for a file endpoint; safe to show."""
    try:
        payload = response.json()
        message = payload["error"]["message"]
        return str(message)[:200]
    except (ValueError, KeyError, TypeError):
        return response.reason_phrase or ""


class TokenSource:
    """Turns the refresh token into short-lived access tokens, kept in memory only."""

    def __init__(self, client: OAuthClient, tokens: TokenFile, http: httpx.Client) -> None:
        self._client = client
        self._tokens = tokens
        self._http = http
        self._access_token: str | None = None
        self._expires_at = 0.0

    def __repr__(self) -> str:
        return "TokenSource(<redacted>)"

    def invalidate(self) -> None:
        self._access_token = None
        self._expires_at = 0.0

    def access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        try:
            response = self._http.post(
                self._tokens.token_uri,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._tokens.refresh_token,
                    "client_id": self._client.client_id,
                    "client_secret": self._client.client_secret,
                },
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise StoreError(f"Google token endpoint unreachable ({type(exc).__name__})") from None
        if response.status_code != 200:
            # Never echo the token endpoint's body: it may describe the credential.
            raise StoreError(
                f"Google refused to refresh the Drive access token (HTTP "
                f"{response.status_code}); the consent may have been revoked or expired: "
                "run `python -m oak_binder.vault_login` again"
            )
        try:
            payload = response.json()
            token = str(payload["access_token"])
            lifetime = float(payload.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError):
            raise StoreError("Google token endpoint returned an unusable response") from None
        self._access_token = token
        self._expires_at = time.time() + lifetime
        return token


# --- the store ---------------------------------------------------------------------------------


class GoogleDriveStore:
    """The Binder's attachment store on one Google Drive folder. See the module docstring."""

    def __init__(
        self,
        folder_id: str,
        tokens: TokenSource,
        http: httpx.Client,
        *,
        api_base: str = API_BASE,
        upload_base: str = UPLOAD_BASE,
    ) -> None:
        if not folder_id.strip():
            raise Invalid("the vault folder id is blank")
        self.folder_id = folder_id.strip()
        self._tokens = tokens
        self._http = http
        self._api = api_base.rstrip("/")
        self._upload = upload_base.rstrip("/")

    def __repr__(self) -> str:
        return f"GoogleDriveStore(folder={self.folder_id})"

    @classmethod
    def from_settings(
        cls, settings: Settings, http: httpx.Client | None = None
    ) -> GoogleDriveStore:
        if not settings.vault_client_file or not settings.vault_credential:
            raise StoreUnavailable(
                "OAK_STORE=vault needs OAK_VAULT_CLIENT_FILE and OAK_VAULT_CREDENTIAL (D27)"
            )
        client = load_client(Path(settings.vault_client_file))
        tokens = TokenFile.load(Path(settings.vault_credential))
        if DRIVE_SCOPE not in tokens.scope.split():
            raise StoreUnavailable(
                "the Drive token was not granted the drive scope the vault folder needs; run "
                "`python -m oak_binder.vault_login` again (D27)"
            )
        web = http or httpx.Client(timeout=TIMEOUT)
        base = (settings.vault_url or API_BASE).rstrip("/")
        return cls(
            settings.vault_container or "",
            TokenSource(client, tokens, web),
            web,
            api_base=base,
            upload_base=base.replace("/drive/v3", "/upload/drive/v3"),
        )

    # -- HTTP ----------------------------------------------------------------------------------

    def _send(self, method: str, url: str, *, what: str, **kwargs: Any) -> httpx.Response:
        """One authenticated call. A 401 is retried once with a fresh token. Transport faults
        and server errors become StoreUnavailable; 404 and 403/409 are left to the caller."""
        for attempt in (1, 2):
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["Authorization"] = f"Bearer {self._tokens.access_token()}"
            try:
                response = self._http.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                raise StoreError(
                    f"Google Drive unreachable while trying to {what} ({type(exc).__name__})"
                ) from None
            if response.status_code == 401 and attempt == 1:
                self._tokens.invalidate()
                continue
            break
        if response.status_code >= 500 or response.status_code == 429:
            raise StoreError(
                f"Google Drive could not {what} (HTTP {response.status_code}: "
                f"{_drive_message(response)})"
            )
        if response.status_code == 401:
            raise StoreError(
                f"Google Drive rejected the vault's credential while trying to {what}; run "
                "`python -m oak_binder.vault_login` again"
            )
        return response

    def _metadata(self, doc_id: str) -> dict[str, Any] | None:
        response = self._send(
            "GET",
            f"{self._api}/files/{doc_id}",
            what=f"read the details of document {doc_id[:12]}…",
            params={"fields": METADATA_FIELDS, "supportsAllDrives": "true"},
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise StoreError(
                f"Google Drive refused the details of document {doc_id[:12]}… "
                f"(HTTP {response.status_code}: {_drive_message(response)})"
            )
        payload: dict[str, Any] = response.json()
        return payload

    def _in_vault(self, meta: dict[str, Any]) -> bool:
        """Only a file this adapter filed in the vault folder is the Binder's to touch."""
        parents = meta.get("parents") or []
        marker = (meta.get("appProperties") or {}).get(MARKER_KEY)
        return (
            parents == [self.folder_id]
            and marker == MARKER_VALUE
            and not meta.get("trashed", False)
            and meta.get("mimeType") != FOLDER_MIME
        )

    # -- the folder ----------------------------------------------------------------------------

    def folder_info(self) -> dict[str, Any]:
        """The vault folder's name and whether this account may file into it. Used by the
        login check; raises with a plain reason when the folder cannot be used."""
        response = self._send(
            "GET",
            f"{self._api}/files/{self.folder_id}",
            what="read the vault folder",
            params={"fields": FOLDER_FIELDS, "supportsAllDrives": "true"},
        )
        if response.status_code == 404:
            raise StoreError(
                f"the vault folder {self.folder_id} is not visible to this account and scope "
                "(Drive answered 404): check the folder id and that the consenting account "
                "owns or can edit the folder"
            )
        if response.status_code != 200:
            raise StoreError(
                f"Google Drive refused the vault folder (HTTP {response.status_code}: "
                f"{_drive_message(response)})"
            )
        meta: dict[str, Any] = response.json()
        if meta.get("mimeType") != FOLDER_MIME:
            raise StoreError(f"{self.folder_id} is not a folder (it is {meta.get('mimeType')})")
        if meta.get("trashed"):
            raise StoreError(f"the vault folder {meta.get('name')!r} is in the Drive trash")
        if not (meta.get("capabilities") or {}).get("canAddChildren", False):
            raise StoreError(f"this account may not add files to the folder {meta.get('name')!r}")
        return {"id": meta["id"], "name": meta.get("name"), "can_add_children": True}

    # -- AttachmentStore -----------------------------------------------------------------------

    def put(self, data: bytes, *, filename: str, media_type: str) -> str:
        digest = sha256_of_bytes(data)
        metadata = {
            "name": filename,
            "mimeType": media_type,
            "parents": [self.folder_id],
            "appProperties": {MARKER_KEY: MARKER_VALUE, "sha256": digest},
        }
        start = self._send(
            "POST",
            f"{self._upload}/files",
            what=f"start uploading {filename}",
            params={
                "uploadType": "resumable",
                "supportsAllDrives": "true",
                "fields": METADATA_FIELDS,
            },
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": media_type,
                "X-Upload-Content-Length": str(len(data)),
            },
            content=json.dumps(metadata).encode("utf-8"),
        )
        if start.status_code != 200 or not start.headers.get("Location"):
            raise StoreError(
                f"Google Drive refused to start the upload of {filename} "
                f"(HTTP {start.status_code}: {_drive_message(start)})"
            )
        session_url = start.headers["Location"]
        upload = self._send(
            "PUT",
            session_url,
            what=f"upload {filename}",
            headers={"Content-Type": media_type, "Content-Length": str(len(data))},
            content=data,
        )
        if upload.status_code not in (200, 201):
            raise StoreError(
                f"Google Drive did not accept the bytes of {filename} "
                f"(HTTP {upload.status_code}: {_drive_message(upload)})"
            )
        created: dict[str, Any] = upload.json()
        doc_id = str(created.get("id") or "")
        if not doc_id:
            raise StoreError(f"Google Drive returned no id for the uploaded {filename}")
        try:
            self._verify_upload(doc_id, data, digest, created)
            self._lock(doc_id, filename)
        except StoreUnavailable:
            self._discard(doc_id)
            raise
        return doc_id

    def _verify_upload(
        self, doc_id: str, data: bytes, digest: str, created: dict[str, Any]
    ) -> None:
        """What Drive stored must be what was sent: by Drive's SHA-256 when it reports one, by
        its MD5 otherwise, and by reading the bytes back when it reports neither."""
        if created.get("size") is not None and int(created["size"]) != len(data):
            raise StoreError(f"Google Drive stored {created['size']} bytes of {len(data)} sent")
        reported = created.get("sha256Checksum")
        if reported:
            if str(reported).lower() != digest:
                raise StoreError("Google Drive's SHA-256 of the upload differs from the file's")
            return
        md5 = created.get("md5Checksum")
        if md5:
            if str(md5).lower() != hashlib.md5(data).hexdigest():  # noqa: S324 (integrity, not security)
                raise StoreError("Google Drive's MD5 of the upload differs from the file's")
            return
        if sha256_of_bytes(self._download(doc_id)) != digest:
            raise StoreError("the bytes read back from Google Drive differ from the file's")

    def _lock(self, doc_id: str, filename: str) -> None:
        response = self._send(
            "PATCH",
            f"{self._api}/files/{doc_id}",
            what=f"lock {filename} against edits",
            params={"supportsAllDrives": "true", "fields": "id,contentRestrictions"},
            headers={"Content-Type": "application/json; charset=UTF-8"},
            content=json.dumps(
                {
                    "contentRestrictions": [
                        {"readOnly": True, "reason": "SA 230 audit evidence: write-once"}
                    ]
                }
            ).encode("utf-8"),
        )
        if response.status_code != 200:
            raise StoreError(
                f"Google Drive would not lock {filename} against edits "
                f"(HTTP {response.status_code}: {_drive_message(response)})"
            )

    def _discard(self, doc_id: str) -> None:
        """Best effort: remove a file whose upload did not verify or lock."""
        try:
            self._send(
                "DELETE",
                f"{self._api}/files/{doc_id}",
                what="discard an unverified upload",
                params={"supportsAllDrives": "true"},
            )
        except StoreUnavailable:
            pass

    def _download(self, doc_id: str) -> bytes:
        response = self._send(
            "GET",
            f"{self._api}/files/{doc_id}",
            what=f"download document {doc_id[:12]}…",
            params={"alt": "media", "supportsAllDrives": "true"},
        )
        if response.status_code == 404:
            raise NotFound(f"document {doc_id[:12]}… is missing from the Drive vault")
        if response.status_code != 200:
            raise StoreError(
                f"Google Drive refused to serve document {doc_id[:12]}… "
                f"(HTTP {response.status_code}: {_drive_message(response)})"
            )
        return response.content

    def read(self, doc_id: str) -> bytes:
        meta = self._metadata(doc_id)
        if meta is None or not self._in_vault(meta):
            raise NotFound(
                f"document {doc_id[:12]}… is missing from the Drive vault folder (absent, "
                "trashed, moved or not filed by the Binder)"
            )
        return self._download(doc_id)

    def exists(self, doc_id: str) -> bool:
        meta = self._metadata(doc_id)
        return meta is not None and self._in_vault(meta)

    def delete(self, doc_id: str) -> bool:
        meta = self._metadata(doc_id)
        if meta is None:
            return False
        if not self._in_vault(meta):
            raise Conflict(
                f"refusing to delete {doc_id[:12]}…: it is not a Binder document in the vault "
                "folder"
            )
        response = self._send(
            "DELETE",
            f"{self._api}/files/{doc_id}",
            what=f"delete document {doc_id[:12]}…",
            params={"supportsAllDrives": "true"},
        )
        if response.status_code == 404:
            return False
        if response.status_code not in (200, 204):
            raise StoreError(
                f"Google Drive refused to delete document {doc_id[:12]}… "
                f"(HTTP {response.status_code}: {_drive_message(response)})"
            )
        return True


# --- the one-time consent (installed-application flow with PKCE) ------------------------------


@dataclass(frozen=True)
class PendingAuthorization:
    url: str
    state: str
    verifier: str
    redirect_uri: str


def begin_authorization(client: OAuthClient, redirect_uri: str) -> PendingAuthorization:
    """The consent URL for the full drive scope, with PKCE and a state token."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    state = secrets.token_urlsafe(24)
    query = urlencode(
        {
            "client_id": client.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": DRIVE_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    return PendingAuthorization(f"{client.auth_uri}?{query}", state, verifier, redirect_uri)


def exchange_code(
    http: httpx.Client, client: OAuthClient, pending: PendingAuthorization, code: str
) -> TokenFile:
    """Trade the authorization code for a refresh token. Nothing from the response is
    echoed on failure."""
    try:
        response = http.post(
            client.token_uri,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client.client_id,
                "client_secret": client.client_secret,
                "redirect_uri": pending.redirect_uri,
                "code_verifier": pending.verifier,
            },
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise StoreError(f"Google token endpoint unreachable ({type(exc).__name__})") from None
    if response.status_code != 200:
        raise StoreError(
            f"Google refused the authorization code (HTTP {response.status_code}); start the "
            "login again"
        )
    try:
        payload = response.json()
        refresh = str(payload["refresh_token"])
        scope = str(payload.get("scope", DRIVE_SCOPE))
    except (ValueError, KeyError, TypeError):
        raise StoreError(
            "Google did not return a refresh token; the consent must use access_type=offline "
            "and prompt=consent, and the client must be a Desktop client"
        ) from None
    if DRIVE_SCOPE not in scope.split():
        raise StoreError("the account did not grant the Drive scope the vault folder needs")
    return TokenFile(
        refresh_token=refresh,
        scope=scope,
        token_uri=client.token_uri,
        obtained_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
