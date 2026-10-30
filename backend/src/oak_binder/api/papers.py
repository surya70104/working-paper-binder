from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from oak_binder.api.deps import CurrentUser, DbSession, Now
from oak_binder.errors import Invalid
from oak_binder.models import BinderState
from oak_binder.schemas.papers import PaperOut, PaperPatch, VersionOut
from oak_binder.schemas.xrefs import XrefOut
from oak_binder.services import access, assembly, attachments, papers, xrefs

router = APIRouter(prefix="/api/papers", tags=["papers"])


def paper_out(session: DbSession, paper_id: uuid.UUID) -> PaperOut:
    paper = papers.get_paper(session, paper_id)
    binder = papers.binder_of(session, paper)
    return PaperOut.build(
        paper,
        papers.versions(session, paper),
        attachments.for_paper(session, paper),
        binder.state,
        papers.open_review_notes(session, paper),
        [XrefOut.build(session, binder, paper, x) for x in xrefs.for_paper(session, paper)],
    )


@router.get("/{paper_id}")
def get_paper(paper_id: uuid.UUID, request: Request, session: DbSession, now: Now) -> PaperOut:
    paper = papers.get_paper(session, paper_id)
    binder = papers.binder_of(session, paper)
    access.record(session, binder, access.reader(request, binder), f"paper {paper.ref}", now)
    return paper_out(session, paper_id)


@router.patch("/{paper_id}")
def patch_paper(
    paper_id: uuid.UUID, payload: PaperPatch, session: DbSession, user: CurrentUser, now: Now
) -> PaperOut:
    paper = papers.get_paper(session, paper_id)
    changes = payload.model_dump(exclude_unset=True)
    reason = changes.pop("amendment_reason", None)
    binder = papers.binder_of(session, paper)
    if binder.state == BinderState.ASSEMBLED:
        assembly.amend(session, paper, changes, reason=reason, user=user, now=now)
    else:
        if reason is not None:
            raise Invalid(
                "amendment_reason applies to an assembled binder only; this binder is "
                f"{binder.state}, so edit the paper directly"
            )
        papers.update_paper(session, paper, changes)
    return paper_out(session, paper_id)


@router.get("/{paper_id}/versions")
def get_versions(
    paper_id: uuid.UUID, request: Request, session: DbSession, now: Now
) -> list[VersionOut]:
    paper = papers.get_paper(session, paper_id)
    binder = papers.binder_of(session, paper)
    access.record(session, binder, access.reader(request, binder), f"versions of {paper.ref}", now)
    return [VersionOut.model_validate(v) for v in papers.versions(session, paper)]


@router.post("/{paper_id}/prepare")
def prepare(paper_id: uuid.UUID, session: DbSession, user: CurrentUser, now: Now) -> PaperOut:
    papers.prepare(session, papers.get_paper(session, paper_id), user, now)
    return paper_out(session, paper_id)


@router.post("/{paper_id}/submit")
def submit(paper_id: uuid.UUID, session: DbSession) -> PaperOut:
    papers.submit_for_review(session, papers.get_paper(session, paper_id))
    return paper_out(session, paper_id)


@router.post("/{paper_id}/review")
def review(paper_id: uuid.UUID, session: DbSession, user: CurrentUser, now: Now) -> PaperOut:
    papers.review(session, papers.get_paper(session, paper_id), user, now)
    return paper_out(session, paper_id)


@router.post("/{paper_id}/sign-off")
def sign_off(paper_id: uuid.UUID, session: DbSession, user: CurrentUser, now: Now) -> PaperOut:
    papers.sign_off(session, papers.get_paper(session, paper_id), user, now)
    return paper_out(session, paper_id)
