"""Retention and purge (spec 3G, 8.7; D18).

The seven-year clock is the binder's retention_until, fixed from the report date by the
database. Purge is refused before it. After it, purge destroys the content, which is the
attachment files and their rows, and leaves the paper and version rows with their hashes:
those rows are append-only and the application role cannot delete them, and keeping the
hashed skeleton is what lets the firm prove what the file contained. The purge writes its
own append-only record.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from oak_binder.errors import Conflict
from oak_binder.models import Binder, BinderEvent, BinderState, EventKind, Wp, WpAttachment
from oak_binder.services.assembly import record
from oak_binder.services.attachments import AttachmentStore


def purge_allowed_from(binder: Binder) -> date | None:
    return binder.retention_until


def purge(
    session: Session,
    store: AttachmentStore,
    binder: Binder,
    *,
    user: str,
    today: date,
    now: datetime,
) -> BinderEvent:
    if binder.state == BinderState.PURGED:
        raise Conflict(f"binder for {binder.engagement!r} is already purged")
    if binder.state != BinderState.ASSEMBLED:
        raise Conflict("only an assembled file is retained and can be purged")
    until = purge_allowed_from(binder)
    if until is None or today < until:
        raise Conflict(
            f"retention runs until {until}; purge before that date is refused (spec 3G, 8.7)"
        )
    rows = session.scalars(
        select(WpAttachment).join(Wp, Wp.id == WpAttachment.wp_id).where(Wp.binder_id == binder.id)
    ).all()
    hashes = sorted({r.sha256 for r in rows})
    for row in rows:
        session.delete(row)
    session.flush()
    deleted_files = 0
    for digest in hashes:
        still_referenced = session.scalar(
            select(func.count()).select_from(WpAttachment).where(WpAttachment.sha256 == digest)
        )
        if not still_referenced and store.delete(digest):
            deleted_files += 1
    binder.state = BinderState.PURGED
    session.flush()
    return record(
        session,
        binder,
        EventKind.PURGED,
        user,
        now,
        details={
            "retention_until": until.isoformat(),
            "attachment_rows_deleted": len(rows),
            "files_deleted": deleted_files,
            "retained": "paper and version rows with their content hashes (D18)",
        },
    )
