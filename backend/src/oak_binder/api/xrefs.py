"""Cross-references on a paper (spec 3B, 3E): add while the binder is open, list in and out,
remove before assembly."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response, status

from oak_binder.api.deps import CurrentUser, DbSession, Now, Spine
from oak_binder.api.papers import paper_out
from oak_binder.schemas.papers import PaperOut
from oak_binder.schemas.xref_map import FsLinesOut, XrefMapOut
from oak_binder.schemas.xrefs import XrefCreate, XrefOut
from oak_binder.services import access, binders, fs_lines, papers, xref_map, xrefs

router = APIRouter(tags=["cross-references"])


@router.get("/api/papers/{paper_id}/xrefs")
def list_for_paper(
    paper_id: uuid.UUID, request: Request, session: DbSession, now: Now, spine: Spine
) -> list[XrefOut]:
    paper = papers.get_paper(session, paper_id)
    binder = papers.binder_of(session, paper)
    access.record(
        session,
        binder,
        access.reader(request, binder),
        f"cross-references of {paper.ref}",
        now,
    )
    lines = fs_lines.for_binder(spine, binder)
    return [
        XrefOut.build(session, binder, paper, x, lines) for x in xrefs.for_paper(session, paper)
    ]


@router.post("/api/papers/{paper_id}/xrefs", status_code=status.HTTP_201_CREATED)
def add(
    paper_id: uuid.UUID,
    body: XrefCreate,
    session: DbSession,
    user: CurrentUser,
    now: Now,
    spine: Spine,
) -> PaperOut:
    paper = papers.get_paper(session, paper_id)
    lines = (
        fs_lines.for_binder(spine, papers.binder_of(session, paper))
        if body.to_fs_line is not None
        else None
    )
    xrefs.add(
        session,
        paper,
        to_wp=body.to_wp,
        to_fs_line=body.to_fs_line,
        to_vault_doc=body.to_vault_doc,
        direction=body.direction,
        user=user,
        now=now,
        lines=lines,
    )
    return paper_out(session, paper_id, spine)


@router.get("/api/binders/{binder_id}/fs-lines")
def binder_fs_lines(
    binder_id: uuid.UUID, request: Request, session: DbSession, now: Now, spine: Spine
) -> FsLinesOut:
    """The financial-statement lines a reference may name: the linked Spine version's
    presentation lines by stable head_id, or why there are none (D30)."""
    binder = binders.get_binder(session, binder_id)
    access.record(session, binder, access.reader(request, binder), "FS lines", now)
    return FsLinesOut.build(fs_lines.for_binder(spine, binder))


@router.get("/api/binders/{binder_id}/xref-map")
def binder_xref_map(
    binder_id: uuid.UUID, request: Request, session: DbSession, now: Now, spine: Spine
) -> XrefMapOut:
    """Screen 4 (spec 5): FS line to lead schedule to paper to document (D30)."""
    binder = binders.get_binder(session, binder_id)
    access.record(session, binder, access.reader(request, binder), "cross-reference map", now)
    return XrefMapOut.build(xref_map.build(session, binder, fs_lines.for_binder(spine, binder)))


@router.delete("/api/xrefs/{xref_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(xref_id: uuid.UUID, session: DbSession) -> Response:
    xrefs.remove(session, xrefs.get(session, xref_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/xrefs/{xref_id}/confirm")
def confirm(
    xref_id: uuid.UUID, session: DbSession, user: CurrentUser, now: Now, spine: Spine
) -> PaperOut:
    """Confirm a reference whose target paper was amended since the reference was made (spec
    3E "superseded"; D36): records who, when and the target's current version, and the
    reference stops blocking assembly. 409 when the target has not changed."""
    xref = xrefs.confirm(session, xrefs.get(session, xref_id), user=user, now=now)
    return paper_out(session, xref.from_wp, spine)
