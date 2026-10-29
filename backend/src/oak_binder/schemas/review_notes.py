from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from oak_binder.services.review_notes import Note


class NoteRaise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class NoteAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to: str


class NoteRespond(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class NoteStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: int
    state: str
    text: str | None
    assigned_to: str | None
    actor: str
    at: datetime


class NoteOut(BaseModel):
    note_id: uuid.UUID
    wp_id: uuid.UUID
    state: str
    open: bool
    text: str
    raised_by: str
    raised_at: datetime
    assigned_to: str | None
    response: str | None
    responded_at: datetime | None
    cleared_by: str | None
    cleared_at: datetime | None
    steps: list[NoteStepOut]

    @classmethod
    def build(cls, note: Note) -> NoteOut:
        return cls(
            note_id=note.note_id,
            wp_id=note.wp_id,
            state=note.state,
            open=note.open,
            text=note.text,
            raised_by=note.raised_by,
            raised_at=note.raised_at,
            assigned_to=note.assigned_to,
            response=note.response,
            responded_at=note.responded_at,
            cleared_by=note.cleared_by,
            cleared_at=note.cleared_at,
            steps=[NoteStepOut.model_validate(s) for s in note.steps],
        )


class BinderNoteOut(NoteOut):
    """Screen 3 (spec 5): what is open, raised by whom, assigned to whom, blocking what."""

    ref: str
    title: str
    paper_status: str
