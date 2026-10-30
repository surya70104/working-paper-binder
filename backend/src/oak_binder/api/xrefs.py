"""Cross-references on a paper (spec 3B, 3E): add while the binder is open, list in and out,
remove before assembly."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response, status

from oak_binder.api.deps import CurrentUser, DbSession, Now
from oak_binder.api.papers import paper_out
from oak_binder.schemas.papers import PaperOut
from oak_binder.schemas.xrefs import XrefCreate, XrefOut
from oak_binder.services import access, papers, xrefs

router = APIRouter(tags=["cross-references"])


@router.get("/api/papers/{paper_id}/xrefs")
def list_for_paper(
    paper_id: uuid.UUID, request: Request, session: DbSession, now: Now
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
    return [XrefOut.build(session, binder, paper, x) for x in xrefs.for_paper(session, paper)]


@router.post("/api/papers/{paper_id}/xrefs", status_code=status.HTTP_201_CREATED)
def add(
    paper_id: uuid.UUID, body: XrefCreate, session: DbSession, user: CurrentUser, now: Now
) -> PaperOut:
    paper = papers.get_paper(session, paper_id)
    xrefs.add(
        session,
        paper,
        to_wp=body.to_wp,
        to_fs_line=body.to_fs_line,
        to_vault_doc=body.to_vault_doc,
        direction=body.direction,
        user=user,
        now=now,
    )
    return paper_out(session, paper_id)


@router.delete("/api/xrefs/{xref_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(xref_id: uuid.UUID, session: DbSession) -> Response:
    xrefs.remove(session, xrefs.get(session, xref_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
