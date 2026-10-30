"""Review notes (spec 3D, 5.3): raise on a paper, then assign, respond, clear."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from oak_binder.api.deps import CurrentUser, DbSession, Now
from oak_binder.schemas.review_notes import (
    BinderNoteOut,
    NoteAssign,
    NoteOut,
    NoteRaise,
    NoteRespond,
)
from oak_binder.services import access, binders, papers, review_notes

router = APIRouter(tags=["review-notes"])


@router.get("/api/papers/{paper_id}/review-notes")
def list_for_paper(
    paper_id: uuid.UUID, request: Request, session: DbSession, now: Now
) -> list[NoteOut]:
    paper = papers.get_paper(session, paper_id)
    binder = papers.binder_of(session, paper)
    access.record(
        session, binder, access.reader(request, binder), f"review notes of {paper.ref}", now
    )
    return [NoteOut.build(n) for n in review_notes.for_paper(session, paper)]


@router.post("/api/papers/{paper_id}/review-notes", status_code=status.HTTP_201_CREATED)
def raise_note(
    paper_id: uuid.UUID, payload: NoteRaise, session: DbSession, user: CurrentUser, now: Now
) -> NoteOut:
    paper = papers.get_paper(session, paper_id)
    papers.require_not_purged(papers.binder_of(session, paper))
    return NoteOut.build(
        review_notes.raise_note(session, paper, text=payload.text, user=user, now=now)
    )


@router.get("/api/review-notes/{note_id}")
def get_note(note_id: uuid.UUID, request: Request, session: DbSession, now: Now) -> NoteOut:
    note = review_notes.get_note(session, note_id)
    paper = papers.get_paper(session, note.wp_id)
    binder = papers.binder_of(session, paper)
    access.record(
        session, binder, access.reader(request, binder), f"review note of {paper.ref}", now
    )
    return NoteOut.build(note)


def _live_note(session: DbSession, note_id: uuid.UUID) -> review_notes.Note:
    """The note, provided its binder has not been purged: a purged file takes no steps."""
    note = review_notes.get_note(session, note_id)
    paper = papers.get_paper(session, note.wp_id)
    papers.require_not_purged(papers.binder_of(session, paper))
    return note


@router.post("/api/review-notes/{note_id}/assign")
def assign(
    note_id: uuid.UUID, payload: NoteAssign, session: DbSession, user: CurrentUser, now: Now
) -> NoteOut:
    note = _live_note(session, note_id)
    return NoteOut.build(
        review_notes.assign(session, note, assigned_to=payload.assigned_to, user=user, now=now)
    )


@router.post("/api/review-notes/{note_id}/respond")
def respond(
    note_id: uuid.UUID, payload: NoteRespond, session: DbSession, user: CurrentUser, now: Now
) -> NoteOut:
    note = _live_note(session, note_id)
    return NoteOut.build(review_notes.respond(session, note, text=payload.text, user=user, now=now))


@router.post("/api/review-notes/{note_id}/clear")
def clear(note_id: uuid.UUID, session: DbSession, user: CurrentUser, now: Now) -> NoteOut:
    note = _live_note(session, note_id)
    return NoteOut.build(review_notes.clear(session, note, user=user, now=now))


@router.get("/api/binders/{binder_id}/review-notes")
def list_for_binder(
    binder_id: uuid.UUID, request: Request, session: DbSession, now: Now
) -> list[BinderNoteOut]:
    binder = binders.get_binder(session, binder_id)
    access.record(session, binder, access.reader(request, binder), "review notes", now)
    return [
        BinderNoteOut(
            **NoteOut.build(note).model_dump(),
            ref=paper.ref,
            title=paper.title,
            paper_status=paper.status,
        )
        for paper, note in review_notes.for_binder(session, binder_id)
    ]
