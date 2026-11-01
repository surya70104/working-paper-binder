"""The Financial Spine link (spec 3A; D29): what a binder ties to, and the Spine's
engagements and versions for choosing. Read-only towards the Spine."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from oak_binder.api.deps import DbSession, Now
from oak_binder.errors import SpineUnavailable
from oak_binder.schemas.spine import SpineEngagementOut, SpineLinkOut, SpineVersionOut
from oak_binder.services import access, binders, spine_link
from oak_binder.services.spine_client import SpineClient

router = APIRouter(tags=["spine"])


def spine_of(request: Request) -> SpineClient | None:
    client: SpineClient | None = request.app.state.spine_client
    return client


def _configured(request: Request) -> SpineClient:
    client = spine_of(request)
    if client is None:
        raise SpineUnavailable("no Financial Spine is configured (OAK_SPINE_URL)")
    return client


@router.get("/api/binders/{binder_id}/spine")
def binder_spine(
    binder_id: uuid.UUID, request: Request, session: DbSession, now: Now
) -> SpineLinkOut:
    binder = binders.get_binder(session, binder_id)
    access.record(session, binder, access.reader(request, binder), "spine link", now)
    return SpineLinkOut.build(spine_link.status(spine_of(request), binder))


@router.get("/api/spine/engagements/{engagement_id}")
def spine_engagement(engagement_id: uuid.UUID, request: Request) -> SpineEngagementOut:
    return SpineEngagementOut.build(_configured(request).engagement(engagement_id))


@router.get("/api/spine/engagements/{engagement_id}/versions")
def spine_versions(engagement_id: uuid.UUID, request: Request) -> list[SpineVersionOut]:
    return [SpineVersionOut.build(v) for v in _configured(request).versions(engagement_id)]
