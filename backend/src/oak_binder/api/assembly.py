"""Assembly and retention (spec 3F, 3G, screen 5): status with blockers, Assemble, verify,
Produce file, purge."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Request, Response

from oak_binder.api.deps import CurrentUser, DbSession, Now, Today
from oak_binder.schemas.assembly import AssemblyStatusOut, VerificationOut
from oak_binder.services import assembly, binders, produce, retention
from oak_binder.services.attachments import AttachmentStore

router = APIRouter(prefix="/api/binders", tags=["assembly"])


def _store(request: Request) -> AttachmentStore:
    store: AttachmentStore = request.app.state.attachment_store
    return store


def _status(session: DbSession, binder_id: uuid.UUID, today: Today) -> AssemblyStatusOut:
    binder = binders.get_binder(session, binder_id)
    return AssemblyStatusOut.build(
        binder,
        assembly.blockers(session, binder),
        assembly.NOT_CHECKED,
        assembly.latest_manifest(session, binder),
        assembly.events(session, binder),
        today,
    )


@router.get("/{binder_id}/assembly")
def get_assembly(binder_id: uuid.UUID, session: DbSession, today: Today) -> AssemblyStatusOut:
    return _status(session, binder_id, today)


@router.post("/{binder_id}/assemble")
def assemble(
    binder_id: uuid.UUID, session: DbSession, user: CurrentUser, now: Now, today: Today
) -> AssemblyStatusOut:
    assembly.assemble(session, binders.get_binder(session, binder_id), user, now)
    return _status(session, binder_id, today)


@router.get("/{binder_id}/verify")
def verify(binder_id: uuid.UUID, request: Request, session: DbSession) -> VerificationOut:
    binder = binders.get_binder(session, binder_id)
    return VerificationOut.build(assembly.verify(session, _store(request), binder))


@router.get("/{binder_id}/produce")
def produce_file(
    binder_id: uuid.UUID, request: Request, session: DbSession, user: CurrentUser, now: Now
) -> Response:
    binder = binders.get_binder(session, binder_id)
    data = produce.produce(session, _store(request), binder, user=user, now=now)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", binder.engagement).strip("._") or "binder"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}-audit-file.zip"'},
    )


@router.post("/{binder_id}/purge")
def purge(
    binder_id: uuid.UUID,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    now: Now,
    today: Today,
) -> AssemblyStatusOut:
    binder = binders.get_binder(session, binder_id)
    retention.purge(session, _store(request), binder, user=user, today=today, now=now)
    return _status(session, binder_id, today)
