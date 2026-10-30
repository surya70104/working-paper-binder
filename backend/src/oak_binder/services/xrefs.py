"""Cross-references and broken-reference detection (spec 3B, 3E, 3F, 8.3; D26).

A reference is added and removed while the binder is open. Assembly freezes it with the
rest of the file; after assembly nothing is deleted (spec 3F), so references are not
changed either.

Broken references are detected wherever the data allows:

- a paper target must be a paper of the same binder: refused at creation and re-checked
  at assembly (a paper is never deleted, so the check holds by the foreign key; it is kept
  so that the blocker list says what was checked);
- a document target must be a document some paper of this binder still carries: when the
  only attachment that carried it is removed, the reference is broken and blocks assembly;
- a Spine line cannot be checked: the Spine is not part of this product (D21). Those
  references are listed as *not checked*, never counted as clear.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from oak_binder.errors import Conflict, Invalid, NotFound
from oak_binder.models import Binder, BinderState, Wp, WpAttachment, Xref
from oak_binder.models.xref import Direction

MAX_FS_LINE = 200


@dataclass(frozen=True)
class Broken:
    xref: Xref
    from_ref: str
    detail: str


def _target_label(session: Session, xref: Xref) -> str:
    if xref.to_wp is not None:
        target = session.get(Wp, xref.to_wp)
        return f"paper {target.ref}" if target else f"paper {xref.to_wp}"
    if xref.to_fs_line is not None:
        return f"FS line {xref.to_fs_line!r}"
    return f"document {xref.to_vault_doc}"


def _document_present(session: Session, binder: Binder, doc_id: str) -> bool:
    return (
        session.scalar(
            select(WpAttachment.id)
            .join(Wp, Wp.id == WpAttachment.wp_id)
            .where(Wp.binder_id == binder.id, WpAttachment.vault_doc_id == doc_id)
            .limit(1)
        )
        is not None
    )


def document_attachment(session: Session, binder: Binder, doc_id: str) -> WpAttachment | None:
    """The attachment the document is filed as in this binder (first by paper reference), or
    None when no paper carries it. The link target for a document reference."""
    return session.scalar(
        select(WpAttachment)
        .join(Wp, Wp.id == WpAttachment.wp_id)
        .where(Wp.binder_id == binder.id, WpAttachment.vault_doc_id == doc_id)
        .order_by(Wp.ref, WpAttachment.filename)
        .limit(1)
    )


def add(
    session: Session,
    paper: Wp,
    *,
    to_wp: uuid.UUID | None,
    to_fs_line: str | None,
    to_vault_doc: str | None,
    direction: str,
    user: str,
    now: datetime,
) -> Xref:
    binder = session.get(Binder, paper.binder_id)
    assert binder is not None  # noqa: S101
    if binder.state != BinderState.OPEN:
        raise Conflict(
            f"binder for {binder.engagement!r} is {binder.state}: cross-references are frozen "
            "with the file at assembly (spec 3F)"
        )
    if direction not in {d.value for d in Direction}:
        raise Invalid("direction must be 'to' (this paper refers to the target) or 'from'")
    to_fs_line = (to_fs_line or "").strip() or None
    to_vault_doc = (to_vault_doc or "").strip() or None
    targets = [t for t in (to_wp, to_fs_line, to_vault_doc) if t is not None]
    if len(targets) != 1:
        raise Invalid(
            "a cross-reference names exactly one target: a paper, an FS line or a document"
        )
    if to_wp is not None:
        if to_wp == paper.id:
            raise Invalid(f"{paper.ref} cannot refer to itself")
        target = session.get(Wp, to_wp)
        if target is None or target.binder_id != paper.binder_id:
            raise Invalid(f"no paper {to_wp} in this binder: a reference stays within the file")
    if to_fs_line is not None and len(to_fs_line) > MAX_FS_LINE:
        raise Invalid(f"an FS line reference is at most {MAX_FS_LINE} characters")
    if to_vault_doc is not None and not _document_present(session, binder, to_vault_doc):
        raise Invalid(
            f"no paper of this binder carries document {to_vault_doc}: attach it first, then "
            "refer to it"
        )
    row = Xref(
        from_wp=paper.id,
        to_wp=to_wp,
        to_fs_line=to_fs_line,
        to_vault_doc=to_vault_doc,
        direction=direction,
        created_by=user,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def get(session: Session, xref_id: uuid.UUID) -> Xref:
    row = session.get(Xref, xref_id)
    if row is None:
        raise NotFound(f"no cross-reference {xref_id}")
    return row


def remove(session: Session, xref: Xref) -> None:
    paper = session.get(Wp, xref.from_wp)
    assert paper is not None  # noqa: S101
    binder = session.get(Binder, paper.binder_id)
    assert binder is not None  # noqa: S101
    if binder.state != BinderState.OPEN:
        raise Conflict(
            f"binder for {binder.engagement!r} is {binder.state}: after assembly nothing is "
            "deleted (spec 3F)"
        )
    session.delete(xref)
    session.flush()


def for_paper(session: Session, paper: Wp) -> list[Xref]:
    """Every reference that touches the paper: written on it, pointing at it, or pointing
    at a document filed on it (spec 3E: paper to source document, both directions)."""
    documents = select(WpAttachment.vault_doc_id).where(WpAttachment.wp_id == paper.id)
    return list(
        session.scalars(
            select(Xref)
            .where(
                or_(
                    Xref.from_wp == paper.id,
                    Xref.to_wp == paper.id,
                    Xref.to_vault_doc.in_(documents),
                )
            )
            .order_by(Xref.created_at, Xref.id)
        ).all()
    )


def is_outgoing(xref: Xref, paper: Wp) -> bool:
    """Read from ``paper``: does this paper refer out to something (True), or is it referred
    to (False)? A row written here with direction 'to' reads out; one written on another
    paper pointing here with direction 'to' reads in; 'from' reverses each."""
    written_here = xref.from_wp == paper.id
    return written_here == (xref.direction == Direction.TO)


def for_binder(session: Session, binder: Binder) -> list[Xref]:
    return list(
        session.scalars(
            select(Xref)
            .join(Wp, Wp.id == Xref.from_wp)
            .where(Wp.binder_id == binder.id)
            .order_by(Wp.ref, Xref.created_at, Xref.id)
        ).all()
    )


def check(session: Session, binder: Binder, xref: Xref) -> str | None:
    """Why the reference is broken, or None when its target is present. A Spine line is not
    checkable; the caller lists it as not checked."""
    if xref.to_wp is not None:
        target = session.get(Wp, xref.to_wp)
        if target is None:
            return "the paper it points at no longer exists"
        if target.binder_id != binder.id:
            return f"paper {target.ref} belongs to another binder"
        return None
    if xref.to_vault_doc is not None:
        if not _document_present(session, binder, xref.to_vault_doc):
            return "no paper of this binder carries that document any more"
        return None
    return None


def broken(session: Session, binder: Binder) -> list[Broken]:
    found: list[Broken] = []
    for xref in for_binder(session, binder):
        reason = check(session, binder, xref)
        if reason is not None:
            source = session.get(Wp, xref.from_wp)
            assert source is not None  # noqa: S101
            found.append(Broken(xref, source.ref, f"{_target_label(session, xref)}: {reason}"))
    return found


def unchecked_fs_lines(session: Session, binder: Binder) -> int:
    return sum(1 for x in for_binder(session, binder) if x.to_fs_line is not None)
