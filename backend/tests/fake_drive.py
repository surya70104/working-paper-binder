"""A Google Drive double for the vault adapter (D27): the token endpoint and the few file
endpoints the adapter uses, behind ``httpx.MockTransport``. No network.

It records every call so tests can assert what the adapter never does (list, search, update
content, touch files outside the vault folder), and it can misbehave on request: expire the
access token, corrupt an upload, omit checksums, trash or alter a stored file.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from oak_binder.hashing import sha256_of_bytes
from oak_binder.services.google_drive import (
    API_BASE,
    DRIVE_SCOPE,
    FOLDER_MIME,
    TOKEN_URI,
    UPLOAD_BASE,
    GoogleDriveStore,
    OAuthClient,
    TokenFile,
    TokenSource,
)

FOLDER_ID = "1XiA9-vRVldypsN61ZPRj-T3bq1pYGY12"
ACCESS_TOKEN = "fake-access-token"  # noqa: S105
REFRESH_TOKEN = "fake-refresh-token"  # noqa: S105
CLIENT = OAuthClient(client_id="fake-client-id", client_secret="fake-client-secret")  # noqa: S106


@dataclass
class Call:
    method: str
    path: str
    query: dict[str, list[str]]


@dataclass
class FakeFile:
    name: str
    mime_type: str
    parents: list[str]
    data: bytes | None
    app_properties: dict[str, str] = field(default_factory=dict)
    trashed: bool = False
    read_only: bool = False
    can_add_children: bool = True

    def metadata(self, report_sha256: bool) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "id": "",
            "name": self.name,
            "mimeType": self.mime_type,
            "parents": self.parents,
            "trashed": self.trashed,
            "appProperties": self.app_properties,
            "contentRestrictions": [{"readOnly": True}] if self.read_only else [],
            "capabilities": {"canAddChildren": self.can_add_children},
        }
        if self.data is not None:
            meta["size"] = str(len(self.data))
            meta["md5Checksum"] = hashlib.md5(self.data).hexdigest()  # noqa: S324
            if report_sha256:
                meta["sha256Checksum"] = sha256_of_bytes(self.data)
        return meta


class FakeDrive:
    def __init__(self, folder_id: str = FOLDER_ID) -> None:
        self.folder_id = folder_id
        self.files: dict[str, FakeFile] = {
            folder_id: FakeFile("Working Paper Binder Vault", FOLDER_MIME, ["root"], None),
            "outside-1": FakeFile(
                "tax-return.pdf", "application/pdf", ["some-other-folder"], b"%PDF personal"
            ),
        }
        self.calls: list[Call] = []
        self.token_grants: list[str] = []
        self.pending_uploads: dict[str, dict[str, Any]] = {}
        self.access_token = ACCESS_TOKEN
        self.report_sha256 = True
        self.corrupt_uploads = False
        self.refuse_lock = False
        self.fail_with: int | None = None  # make every file call answer this status
        self.transport = httpx.MockTransport(self.handle)

    # -- helpers for tests -------------------------------------------------------------------

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport)

    def store(self) -> GoogleDriveStore:
        http = self.client()
        tokens = TokenSource(
            CLIENT,
            TokenFile(REFRESH_TOKEN, DRIVE_SCOPE, TOKEN_URI, "2026-10-30T00:00:00Z"),
            http,
        )
        return GoogleDriveStore(self.folder_id, tokens, http)

    def vault_files(self) -> dict[str, FakeFile]:
        return {
            k: f
            for k, f in self.files.items()
            if f.parents == [self.folder_id] and f.mime_type != FOLDER_MIME
        }

    def tamper(self, doc_id: str, data: bytes) -> None:
        self.files[doc_id].data = data

    def trash(self, doc_id: str) -> None:
        self.files[doc_id].trashed = True

    def expire_token(self) -> None:
        self.access_token = f"rotated-{uuid.uuid4().hex[:6]}"

    def list_calls(self) -> list[Call]:
        return [c for c in self.calls if c.path == "/drive/v3/files" and c.method == "GET"]

    def touched_outside_vault(self) -> list[Call]:
        """Calls on any file that is neither the vault folder nor a file inside it."""
        inside = set(self.vault_files()) | {self.folder_id}
        found = []
        for call in self.calls:
            if call.path.startswith("/drive/v3/files/"):
                file_id = call.path.rsplit("/", 1)[1]
                if file_id not in inside and file_id in self.files:
                    found.append(call)
        return found

    # -- the double ----------------------------------------------------------------------------

    def _json(
        self, status: int, payload: Any, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers)

    def _error(self, status: int, message: str) -> httpx.Response:
        return self._json(status, {"error": {"code": status, "message": message}})

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        query = parse_qs(url.query)
        if str(request.url).split("?")[0] == TOKEN_URI:
            return self._token(request)
        self.calls.append(Call(request.method, url.path, query))
        if request.headers.get("Authorization") != f"Bearer {self.access_token}":
            return self._error(401, "Invalid Credentials")
        if self.fail_with is not None:
            return self._error(self.fail_with, "Backend Error")
        if url.path == "/upload/drive/v3/files" and request.method == "POST":
            return self._start_upload(request, query)
        if url.path == "/upload/drive/v3/files" and request.method == "PUT":
            return self._finish_upload(request, query)
        if url.path == "/drive/v3/files" and request.method == "GET":
            return self._error(403, "listing is not something the Binder does")
        if url.path.startswith("/drive/v3/files/"):
            file_id = url.path.rsplit("/", 1)[1]
            return self._file(request, file_id, query)
        return self._error(404, "Not Found")

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode("utf-8"))
        grant = form.get("grant_type", [""])[0]
        self.token_grants.append(grant)
        if form.get("client_id", [""])[0] != CLIENT.client_id:
            return self._json(401, {"error": "invalid_client"})
        if grant == "refresh_token":
            if form.get("refresh_token", [""])[0] != REFRESH_TOKEN:
                return self._json(400, {"error": "invalid_grant"})
            return self._json(200, {"access_token": self.access_token, "expires_in": 3600})
        if grant == "authorization_code":
            if form.get("code", [""])[0] != "good-code" or not form.get("code_verifier"):
                return self._json(400, {"error": "invalid_grant"})
            return self._json(
                200,
                {
                    "access_token": self.access_token,
                    "refresh_token": REFRESH_TOKEN,
                    "scope": DRIVE_SCOPE,
                    "expires_in": 3600,
                },
            )
        return self._json(400, {"error": "unsupported_grant_type"})

    def _start_upload(self, request: httpx.Request, query: dict[str, list[str]]) -> httpx.Response:
        if query.get("uploadType") != ["resumable"]:
            return self._error(400, "only resumable uploads are supported here")
        metadata = json.loads(request.content.decode("utf-8"))
        upload_id = uuid.uuid4().hex
        self.pending_uploads[upload_id] = metadata
        location = f"{UPLOAD_BASE}/files?uploadType=resumable&upload_id={upload_id}"
        return httpx.Response(200, headers={"Location": location})

    def _finish_upload(self, request: httpx.Request, query: dict[str, list[str]]) -> httpx.Response:
        upload_id = query.get("upload_id", [""])[0]
        metadata = self.pending_uploads.pop(upload_id, None)
        if metadata is None:
            return self._error(404, "unknown upload session")
        parents = metadata.get("parents") or []
        for parent in parents:
            if parent not in self.files or self.files[parent].mime_type != FOLDER_MIME:
                return self._error(404, f"File not found: {parent}.")
        data = request.content
        if self.corrupt_uploads:
            data = bytes([data[0] ^ 0xFF]) + data[1:]  # same length; only a checksum sees it
        file_id = f"drive-{uuid.uuid4().hex[:16]}"
        self.files[file_id] = FakeFile(
            metadata["name"],
            metadata.get("mimeType", "application/octet-stream"),
            parents,
            data,
            dict(metadata.get("appProperties") or {}),
        )
        meta = self.files[file_id].metadata(self.report_sha256)
        meta["id"] = file_id
        return self._json(200, meta)

    def _file(
        self, request: httpx.Request, file_id: str, query: dict[str, list[str]]
    ) -> httpx.Response:
        item = self.files.get(file_id)
        if item is None:
            return self._error(404, f"File not found: {file_id}.")
        if request.method == "GET":
            if query.get("alt") == ["media"]:
                if item.data is None:
                    return self._error(403, "folders have no content")
                return httpx.Response(200, content=item.data)
            meta = item.metadata(self.report_sha256)
            meta["id"] = file_id
            return self._json(200, meta)
        if request.method == "PATCH":
            if self.refuse_lock:
                return self._error(403, "cannot modify content restrictions")
            body = json.loads(request.content.decode("utf-8"))
            if "contentRestrictions" in body:
                item.read_only = bool(body["contentRestrictions"][0].get("readOnly"))
            return self._json(
                200, {"id": file_id, "contentRestrictions": [{"readOnly": item.read_only}]}
            )
        if request.method == "DELETE":
            del self.files[file_id]
            return httpx.Response(204)
        return self._error(405, "Method Not Allowed")


__all__ = [
    "ACCESS_TOKEN",
    "API_BASE",
    "CLIENT",
    "FOLDER_ID",
    "REFRESH_TOKEN",
    "FakeDrive",
    "FakeFile",
]
