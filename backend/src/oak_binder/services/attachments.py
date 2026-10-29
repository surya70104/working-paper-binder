"""Attachments: native-format files kept in a local write-once store (spec 3B, 3G; D7, D17).

This is a local store, not a vault integration: no vault exists in this project or in the
Financial Spine. Files live under OAK_ATTACHMENTS_DIR, outside anything a web server serves,
at ``<sha256[:2]>/<sha256>``. Bytes are never altered; the same bytes are stored once; every
read recomputes the hash and refuses a mismatch. ``vault_doc_id`` holds the store key so a
vault can take over without a schema change.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path, PurePath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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


class AttachmentStore:
    """Content-addressed, write-once files on local disk."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, sha256: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise Invalid("not a SHA-256 key")
        return self.root / sha256[:2] / sha256

    def put(self, data: bytes) -> str:
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

    def exists(self, sha256: str) -> bool:
        return self.path_for(sha256).exists()

    def read(self, sha256: str) -> bytes:
        """The stored bytes, re-hashed on the way out. A mismatch is refused, not served."""
        path = self.path_for(sha256)
        if not path.exists():
            raise NotFound(f"stored file {sha256[:12]}… is missing from the attachment store")
        data = path.read_bytes()
        if sha256_of_bytes(data) != sha256:
            raise Conflict(
                f"stored file {sha256[:12]}… no longer matches its hash; "
                "the attachment store has been altered"
            )
        return data

    def delete(self, sha256: str) -> bool:
        """Remove a stored file. Only the purge path calls this (spec 3G)."""
        path = self.path_for(sha256)
        if not path.exists():
            return False
        path.unlink()
        return True


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
    key = store.put(data)
    row = WpAttachment(
        wp_id=paper.id,
        wp_version_id=None,
        vault_doc_id=key,
        identifying_chars=(identifying_chars or "").strip() or None,
        sha256=key,
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


def remove(session: Session, paper: Wp, attachment: WpAttachment) -> None:
    """Detach a file before assembly. After assembly nothing is deleted (spec 3F, 8.4).
    The stored bytes stay in the store: another paper may share them, and the hash remains
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
    return store.read(attachment.sha256)
