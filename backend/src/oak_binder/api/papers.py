from __future__ import annotations

import uuid

from fastapi import APIRouter

from oak_binder.api.deps import CurrentUser, DbSession, Now
from oak_binder.models import BinderState
from oak_binder.schemas.papers import PaperOut, PaperPatch, VersionOut
from oak_binder.services import assembly, attachments, papers

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
    )


@router.get("/{paper_id}")
def get_paper(paper_id: uuid.UUID, session: DbSession) -> PaperOut:
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
        papers.update_paper(session, paper, changes)
    return paper_out(session, paper_id)


@router.get("/{paper_id}/versions")
def get_versions(paper_id: uuid.UUID, session: DbSession) -> list[VersionOut]:
    paper = papers.get_paper(session, paper_id)
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
