from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from oak_binder.models import Binder, Wp, Xref
from oak_binder.services import xrefs


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
    # Information only (spec 3E "superseded", reading pending): the target paper's content
    # has changed since this reference was made. Never a blocker.
    target_amended: str | None

    @classmethod
    def build(cls, session: Session, binder: Binder, paper: Wp, xref: Xref) -> XrefOut:
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
            to_vault_doc=xref.to_vault_doc,
            to_filename=filed.filename if filed is not None else None,
            to_attachment_id=filed.id if filed is not None else None,
            to_attachment_ref=filed_on.ref if filed_on is not None else None,
            direction=xref.direction,
            outgoing=xrefs.is_outgoing(xref, paper),
            created_by=xref.created_by,
            created_at=xref.created_at,
            broken=xrefs.check(session, binder, xref),
            checked=xref.to_fs_line is None,
            target_amended=xrefs.target_amended(session, xref),
        )
