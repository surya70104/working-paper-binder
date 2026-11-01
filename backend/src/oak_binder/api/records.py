"""The discussions and departures logs on a binder (spec 2, 3H, 4): record and list."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from oak_binder.api.deps import CurrentUser, DbSession, Now
from oak_binder.schemas.records import DepartureIn, DepartureOut, DiscussionIn, DiscussionOut
from oak_binder.services import access, binders, records

router = APIRouter(prefix="/api/binders", tags=["records"])


@router.get("/{binder_id}/discussions")
def list_discussions(
    binder_id: uuid.UUID, request: Request, session: DbSession, now: Now
) -> list[DiscussionOut]:
    binder = binders.get_binder(session, binder_id)
    access.record(session, binder, access.reader(request, binder), "discussions", now)
    return [DiscussionOut.model_validate(d) for d in records.discussions(session, binder)]


@router.post("/{binder_id}/discussions", status_code=status.HTTP_201_CREATED)
def record_discussion(
    binder_id: uuid.UUID, body: DiscussionIn, session: DbSession, user: CurrentUser, now: Now
) -> DiscussionOut:
    binder = binders.get_binder(session, binder_id)
    row = records.record_discussion(
        session,
        binder,
        date=body.date,
        participants=body.participants,
        matter=body.matter,
        outcome=body.outcome,
        amendment_reason=body.amendment_reason,
        user=user,
        now=now,
    )
    return DiscussionOut.model_validate(row)


@router.get("/{binder_id}/departures")
def list_departures(
    binder_id: uuid.UUID, request: Request, session: DbSession, now: Now
) -> list[DepartureOut]:
    binder = binders.get_binder(session, binder_id)
    access.record(session, binder, access.reader(request, binder), "departures", now)
    return [DepartureOut.model_validate(d) for d in records.departures(session, binder)]


@router.post("/{binder_id}/departures", status_code=status.HTTP_201_CREATED)
def record_departure(
    binder_id: uuid.UUID, body: DepartureIn, session: DbSession, user: CurrentUser, now: Now
) -> DepartureOut:
    binder = binders.get_binder(session, binder_id)
    row = records.record_departure(
        session,
        binder,
        requirement=body.requirement,
        reason=body.reason,
        alternative_procedure=body.alternative_procedure,
        approved_by=body.approved_by,
        amendment_reason=body.amendment_reason,
        user=user,
        now=now,
    )
    return DepartureOut.model_validate(row)
