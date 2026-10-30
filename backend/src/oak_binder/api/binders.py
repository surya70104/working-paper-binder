from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from oak_binder.api.deps import DbSession, Now, Today
from oak_binder.schemas.binders import BinderCreate, BinderOut, BinderPatch, BinderSummary
from oak_binder.schemas.papers import PaperCreate, PaperOut
from oak_binder.services import access, binders, papers

router = APIRouter(prefix="/api/binders", tags=["binders"])


def _out(session: DbSession, binder_id: uuid.UUID, today: Today) -> BinderOut:
    binder = binders.get_binder(session, binder_id)
    return BinderOut.build(binder, binders.build_index(session, binder), today)


@router.get("")
def list_binders(session: DbSession) -> list[BinderSummary]:
    return [BinderSummary.model_validate(b) for b in binders.list_binders(session)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_binder(payload: BinderCreate, session: DbSession, today: Today) -> BinderOut:
    binder = binders.create_binder(
        session,
        engagement=payload.engagement,
        template=payload.template,
        report_date=payload.report_date,
    )
    return _out(session, binder.id, today)


@router.get("/{binder_id}")
def get_binder(
    binder_id: uuid.UUID, request: Request, session: DbSession, today: Today, now: Now
) -> BinderOut:
    binder = binders.get_binder(session, binder_id)
    access.record(session, binder, access.reader(request, binder), "binder", now)
    return _out(session, binder_id, today)


@router.patch("/{binder_id}")
def patch_binder(
    binder_id: uuid.UUID, payload: BinderPatch, session: DbSession, today: Today
) -> BinderOut:
    binder = binders.get_binder(session, binder_id)
    changes = payload.model_dump(exclude_unset=True)
    # Only a request that names report_date changes it; an empty PATCH changes nothing.
    if "report_date" in changes:
        binders.set_report_date(session, binder, changes["report_date"])
    return _out(session, binder_id, today)


@router.post("/{binder_id}/papers", status_code=status.HTTP_201_CREATED)
def create_paper(binder_id: uuid.UUID, payload: PaperCreate, session: DbSession) -> PaperOut:
    binder = binders.get_binder(session, binder_id)
    paper = papers.create_paper(session, binder, payload.model_dump())
    return PaperOut.build(paper, [], [], binder.state)
