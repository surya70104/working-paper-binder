"""Attachments: native-format files behind a storage protocol (spec 3B, 3G; D7, D17, D23).

Two ideas are kept apart on every row:
- ``vault_doc_id`` is the key the store knows the document by. For the local store it is the
  file's SHA-256; for a vault it will be whatever opaque id the vault returns.
- ``sha256`` is the Binder's own hash of the bytes, computed at upload. Every read goes
  through ``verified_read``, which re-hashes what the store returns and refuses a mismatch,
  whatever the store. The integrity rule therefore does not depend on the backend.

Stores implement ``AttachmentStore``: put, read, exists, delete. ``LocalAttachmentStore`` is
the write-once, content-addressed directory under OAK_ATTACHMENTS_DIR, outside anything a
web server serves. ``InMemoryVaultStore`` behaves like a vault (opaque ids, no
content-addressing) and exists for the storage contract tests. The real vault is the
firm's Google Drive folder, ``services.google_drive.GoogleDriveStore`` (D27).
``build_store`` picks the store from OAK_STORE; local is the default.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path, PurePath
from typing import Protocol, runtime_checkable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from oak_binder.config import Settings
from oak_binder.errors import Conflict, Invalid, NotFound, TooLarge, UnsupportedType
from oak_binder.hashing import sha256_of_bytes
from oak_binder.models import Binder, BinderState, Wp, WpAttachment, WpStatus

# Spec 3G names xlsx, pdf and csv as the native formats. The rest are ordinary evidence.
MEDIA_TYPES: dict[str, str] = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@runtime_checkable
class AttachmentStore(Protocol):
    """What any document store must offer the Binder. Keys are opaque document ids."""

    def put(self, data: bytes, *, filename: str, media_type: str) -> str:
        """Store bytes; return the document id. Must never alter or overwrite stored bytes."""

    def read(self, doc_id: str) -> bytes:
        """The stored bytes, or NotFound. Integrity is checked by the caller."""

    def exists(self, doc_id: str) -> bool: ...

    def delete(self, doc_id: str) -> bool:
        """Remove a document; True if it existed. Only the purge path calls this (spec 3G)."""


class LocalAttachmentStore:
    """Content-addressed, write-once files on local disk. The document id is the SHA-256."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, doc_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", doc_id):
            raise Invalid("not a local store key")
        return self.root / doc_id[:2] / doc_id

    def put(self, data: bytes, *, filename: str, media_type: str) -> str:
        """Store bytes under their hash. Identical bytes are stored once; nothing is ever
        overwritten. Returns the key."""
        key = sha256_of_bytes(data)
        target = self.path_for(key)
        if target.exists():
            return key
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
        temp.write_bytes(data)
        os.replace(temp, target)  # atomic: a reader never sees a half-written file
        return key

    def exists(self, doc_id: str) -> bool:
        return self.path_for(doc_id).exists()

    def read(self, doc_id: str) -> bytes:
        path = self.path_for(doc_id)
        if not path.exists():
            raise NotFound(f"stored file {doc_id[:12]}… is missing from the attachment store")
        return path.read_bytes()

    def delete(self, doc_id: str) -> bool:
        path = self.path_for(doc_id)
        if not path.exists():
            return False
        path.unlink()
        return True


class InMemoryVaultStore:
    """A vault stand-in for tests: opaque ids, no content-addressing, and a way to tamper.
    Not for production use."""

    def __init__(self) -> None:
        self.documents: dict[str, tuple[bytes, str, str]] = {}

    def put(self, data: bytes, *, filename: str, media_type: str) -> str:
        doc_id = f"vault-{uuid.uuid4().hex}"
        self.documents[doc_id] = (data, filename, media_type)
        return doc_id

    def read(self, doc_id: str) -> bytes:
        try:
            return self.documents[doc_id][0]
        except KeyError:
            raise NotFound(f"document {doc_id} is missing from the vault") from None

    def exists(self, doc_id: str) -> bool:
        return doc_id in self.documents

    def delete(self, doc_id: str) -> bool:
        return self.documents.pop(doc_id, None) is not None

    def tamper(self, doc_id: str, data: bytes) -> None:
        """Simulate a vault that altered a document behind the Binder's back."""
        _, filename, media_type = self.documents[doc_id]
        self.documents[doc_id] = (data, filename, media_type)


def build_store(settings: Settings) -> AttachmentStore:
    """The store OAK_STORE selects. Relative local paths resolve from the working
    directory, which is backend\\ when run as the README says."""
    if settings.store == "local":
        return LocalAttachmentStore(settings.attachments_dir.resolve())
    # The firm's vault is a Google Drive folder (D27). Imported here so the local store
    # never depends on the HTTP client.
    from oak_binder.services.google_drive import GoogleDriveStore

    return GoogleDriveStore.from_settings(settings)


def verified_read(store: AttachmentStore, attachment: WpAttachment) -> bytes:
    """The attachment's bytes from the store, re-hashed and compared with the hash recorded
    at upload. A mismatch is refused, not served, whichever store is behind it."""
    data = store.read(attachment.vault_doc_id)
    if sha256_of_bytes(data) != attachment.sha256:
        raise Conflict(
            f"stored file {attachment.sha256[:12]}… no longer matches its hash; "
            "the attachment store has been altered"
        )
    return data


def safe_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name.strip()
    if not base or base in {".", ".."}:
        raise Invalid("the attachment needs a file name")
    return base


def media_type_for(filename: str) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext not in MEDIA_TYPES:
        raise UnsupportedType(
            f"{ext or 'a file without an extension'} is not an accepted attachment type; "
            f"accepted: {', '.join(sorted(MEDIA_TYPES))}"
        )
    return MEDIA_TYPES[ext]


def attach(
    session: Session,
    store: AttachmentStore,
    paper: Wp,
    *,
    filename: str,
    data: bytes,
    identifying_chars: str | None,
    user: str,
    now: datetime,
    max_bytes: int,
) -> WpAttachment:
    """Attach bytes to a paper. The paper's content changed, so it returns to draft; the
    file joins the signed record at the next prepare. On an assembled binder the caller
    must go through the amendment path (services.assembly.amend_attach)."""
    binder = session.get(Binder, paper.binder_id)
    assert binder is not None  # noqa: S101
    if binder.state != BinderState.OPEN:
        raise Conflict(
            f"binder for {binder.engagement!r} is {binder.state}; a post-assembly attachment "
            "is an amendment and needs a reason (spec 3F)"
        )
    return _attach_row(
        session,
        store,
        paper,
        filename=filename,
        data=data,
        identifying_chars=identifying_chars,
        user=user,
        now=now,
        max_bytes=max_bytes,
    )


def _existing_doc_id(session: Session, digest: str) -> str | None:
    """A document id already holding these exact bytes, if any row anywhere has them. The
    same evidence attached to two papers is stored once, whatever the store."""
    return session.scalar(
        select(WpAttachment.vault_doc_id).where(WpAttachment.sha256 == digest).limit(1)
    )


def _attach_row(
    session: Session,
    store: AttachmentStore,
    paper: Wp,
    *,
    filename: str,
    data: bytes,
    identifying_chars: str | None,
    user: str,
    now: datetime,
    max_bytes: int,
) -> WpAttachment:
    name = safe_filename(filename)
    media_type = media_type_for(name)
    if not data:
        raise Invalid("the attachment is empty")
    if len(data) > max_bytes:
        raise TooLarge(f"{len(data)} bytes exceeds the limit of {max_bytes} bytes")
    digest = sha256_of_bytes(data)
    doc_id = _existing_doc_id(session, digest)
    if doc_id is None or not store.exists(doc_id):
        doc_id = store.put(data, filename=name, media_type=media_type)
    row = WpAttachment(
        wp_id=paper.id,
        wp_version_id=None,
        vault_doc_id=doc_id,
        identifying_chars=(identifying_chars or "").strip() or None,
        sha256=digest,
        filename=name,
        media_type=media_type,
        size_bytes=len(data),
        attached_by=user,
        attached_at=now,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if "uq_wp_attachment_wp_sha256" in str(exc):
            raise Conflict(f"an identical file is already attached to paper {paper.ref}") from exc
        raise
    if paper.status != WpStatus.DRAFT:
        paper.status = WpStatus.DRAFT
        session.flush()
    return row


def get_attachment(session: Session, attachment_id: uuid.UUID) -> WpAttachment:
    row = session.get(WpAttachment, attachment_id)
    if row is None:
        raise NotFound(f"no attachment {attachment_id}")
    return row


def for_paper(session: Session, paper: Wp) -> list[WpAttachment]:
    return list(
        session.scalars(
            select(WpAttachment)
            .where(WpAttachment.wp_id == paper.id)
            .order_by(WpAttachment.attached_at, WpAttachment.filename)
        ).all()
    )


def references(session: Session, doc_id: str) -> int:
    """How many attachment rows point at a document id."""
    return (
        session.scalar(
            select(func.count())
            .select_from(WpAttachment)
            .where(WpAttachment.vault_doc_id == doc_id)
        )
        or 0
    )


def remove(session: Session, paper: Wp, attachment: WpAttachment) -> None:
    """Detach a file before assembly. After assembly nothing is deleted (spec 3F, 8.4).
    The stored document stays in the store: another paper may share it, and the hash remains
    in every version body that listed the file."""
    binder = session.get(Binder, paper.binder_id)
    assert binder is not None  # noqa: S101
    if binder.state != BinderState.OPEN:
        raise Conflict(
            f"binder for {binder.engagement!r} is {binder.state}: after assembly nothing is "
            "deleted (spec 3F)"
        )
    if attachment.wp_id != paper.id:
        raise NotFound(f"attachment {attachment.id} does not belong to paper {paper.ref}")
    session.delete(attachment)
    if paper.status != WpStatus.DRAFT:
        paper.status = WpStatus.DRAFT
    session.flush()


def link_to_version(session: Session, paper: Wp, version_id: uuid.UUID) -> None:
    """At prepare: attachments not yet part of any signed version join this one."""
    for row in for_paper(session, paper):
        if row.wp_version_id is None:
            row.wp_version_id = version_id
    session.flush()


def content(store: AttachmentStore, attachment: WpAttachment) -> bytes:
    return verified_read(store, attachment)
