"""Attachments: upload to a paper, read back, download the original bytes, remove before
assembly. Files are served by id, never by path (D7)."""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, Request, Response, UploadFile, status

from oak_binder.api.deps import CurrentUser, DbSession, Now
from oak_binder.api.papers import paper_out
from oak_binder.models import BinderState
from oak_binder.schemas.attachments import AttachmentOut
from oak_binder.schemas.papers import PaperOut
from oak_binder.services import assembly, attachments, papers
from oak_binder.services.attachments import AttachmentStore

router = APIRouter(tags=["attachments"])


def store_of(request: Request) -> AttachmentStore:
    store: AttachmentStore = request.app.state.attachment_store
    return store


@router.post("/api/papers/{paper_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload(
    paper_id: uuid.UUID,
    request: Request,
    file: UploadFile,
    session: DbSession,
    user: CurrentUser,
    now: Now,
    identifying_chars: Annotated[str | None, Form()] = None,
    amendment_reason: Annotated[str | None, Form()] = None,
) -> PaperOut:
    paper = papers.get_paper(session, paper_id)
    binder = papers.binder_of(session, paper)
    max_bytes: int = request.app.state.settings.max_upload_bytes
    data = await file.read(max_bytes + 1)  # one byte more than allowed proves an overrun
    if binder.state == BinderState.ASSEMBLED:
        assembly.amend_attach(
            session,
            store_of(request),
            paper,
            filename=file.filename or "",
            data=data,
            identifying_chars=identifying_chars,
            reason=amendment_reason,
            user=user,
            now=now,
            max_bytes=max_bytes,
        )
    else:
        attachments.attach(
            session,
            store_of(request),
            paper,
            filename=file.filename or "",
            data=data,
            identifying_chars=identifying_chars,
            user=user,
            now=now,
            max_bytes=max_bytes,
        )
    return paper_out(session, paper_id)


@router.get("/api/attachments/{attachment_id}")
def get_attachment(attachment_id: uuid.UUID, session: DbSession) -> AttachmentOut:
    return AttachmentOut.model_validate(attachments.get_attachment(session, attachment_id))


@router.get("/api/attachments/{attachment_id}/content")
def download(attachment_id: uuid.UUID, request: Request, session: DbSession) -> Response:
    row = attachments.get_attachment(session, attachment_id)
    data = attachments.content(store_of(request), row)
    ascii_name = row.filename.encode("ascii", "replace").decode("ascii").replace('"', "")
    return Response(
        content=data,
        media_type=row.media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(row.filename)}"
            ),
            "X-Content-SHA256": row.sha256,
        },
    )


@router.delete("/api/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(attachment_id: uuid.UUID, session: DbSession) -> Response:
    row = attachments.get_attachment(session, attachment_id)
    paper = papers.get_paper(session, row.wp_id)
    attachments.remove(session, paper, row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
