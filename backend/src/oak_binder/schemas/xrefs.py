from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from oak_binder.models import Binder, Wp, Xref
from oak_binder.services import xrefs
from oak_binder.services.fs_lines import FsLines


class XrefCreate(BaseModel):
    to_wp: uuid.UUID | None = None
    to_fs_line: str | None = Field(default=None, max_length=xrefs.MAX_FS_LINE)
    to_vault_doc: str | None = None
    direction: str = "to"


class XrefOut(BaseModel):
    id: uuid.UUID
    from_wp: uuid.UUID
    from_ref: str
    to_wp: uuid.UUID | None
    to_ref: str | None
    to_fs_line: str | None
    # The line's label in the linked Spine version, when the line is known (D30).
    to_fs_line_label: str | None
    to_vault_doc: str | None
    to_filename: str | None
    # The attachment the document is filed as, so the reference is clickable (spec 3E).
    to_attachment_id: uuid.UUID | None
    to_attachment_ref: str | None
    direction: str
    # Read from the paper the response belongs to: True when that paper refers out.
    outgoing: bool
    created_by: str
    created_at: datetime
    # Why the reference is broken (spec 3E), None when its target is present, and
    # "not checked" for an FS line, since the Spine does not exist here (D21).
    broken: str | None
    checked: bool
    # Spec 3E "superseded" (D36): the target paper's content has changed since this reference
    # was made or last confirmed. Blocks assembly until confirmed or removed.
    target_amended: str | None
    confirmed_by: str | None
    confirmed_at: datetime | None
    confirmed_version: int | None

    @classmethod
    def build(
        cls,
        session: Session,
        binder: Binder,
        paper: Wp,
        xref: Xref,
        lines: FsLines | None = None,
    ) -> XrefOut:
        source = session.get(Wp, xref.from_wp)
        target = session.get(Wp, xref.to_wp) if xref.to_wp is not None else None
        filed = (
            xrefs.document_attachment(session, binder, xref.to_vault_doc)
            if xref.to_vault_doc is not None
            else None
        )
        filed_on = session.get(Wp, filed.wp_id) if filed is not None else None
        return cls(
            id=xref.id,
            from_wp=xref.from_wp,
            from_ref=source.ref if source else "?",
            to_wp=xref.to_wp,
            to_ref=target.ref if target else None,
            to_fs_line=xref.to_fs_line,
            to_fs_line_label=(
                lines.label(xref.to_fs_line)
                if lines is not None and xref.to_fs_line is not None
                else None
            ),
            to_vault_doc=xref.to_vault_doc,
            to_filename=filed.filename if filed is not None else None,
            to_attachment_id=filed.id if filed is not None else None,
            to_attachment_ref=filed_on.ref if filed_on is not None else None,
            direction=xref.direction,
            outgoing=xrefs.is_outgoing(xref, paper),
            created_by=xref.created_by,
            created_at=xref.created_at,
            broken=xrefs.check(session, binder, xref, lines),
            checked=xref.to_fs_line is None or bool(lines is not None and lines.available),
            target_amended=xrefs.target_amended(session, xref),
            confirmed_by=xref.confirmed_by,
            confirmed_at=xref.confirmed_at,
            confirmed_version=xref.confirmed_version,
        )
