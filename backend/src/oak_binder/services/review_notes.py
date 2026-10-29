"""Review notes: raised -> assigned -> responded -> cleared (spec 3D, 4, 8.2, 8.3).

Every step appends a row; the note's current state is its latest step. A note is open until
it is cleared. An open note blocks the paper's sign-off (papers.sign_off) and the binder's
assembly (assembly.blockers). The chain is the spec's arrow, strictly: a step out of order
is refused. The spec names no rule about who may clear a note, so none is added.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from oak_binder.errors import Conflict, Invalid, NotFound
from oak_binder.models import NoteState, ReviewNote, Wp

NEXT: dict[NoteState, NoteState] = {
    NoteState.RAISED: NoteState.ASSIGNED,
    NoteState.ASSIGNED: NoteState.RESPONDED,
    NoteState.RESPONDED: NoteState.CLEARED,
}


@dataclass(frozen=True)
class Note:
    """A note as it stands now: its latest row plus the text it was raised with."""

    note_id: uuid.UUID
    wp_id: uuid.UUID
    state: str
    text: str
    raised_by: str
    raised_at: datetime
    assigned_to: str | None
    response: str | None
    responded_at: datetime | None
    cleared_by: str | None
    cleared_at: datetime | None
    steps: list[ReviewNote]

    @property
    def open(self) -> bool:
        return self.state != NoteState.CLEARED


def _rows(session: Session, note_id: uuid.UUID) -> list[ReviewNote]:
    return list(
        session.scalars(
            select(ReviewNote).where(ReviewNote.note_id == note_id).order_by(ReviewNote.step)
        ).all()
    )


def _assemble(rows: list[ReviewNote]) -> Note:
    first, last = rows[0], rows[-1]
    responded = next((r for r in rows if r.state == NoteState.RESPONDED), None)
    cleared = next((r for r in rows if r.state == NoteState.CLEARED), None)
    return Note(
        note_id=first.note_id,
        wp_id=first.wp_id,
        state=last.state,
        text=first.text or "",
        raised_by=first.raised_by,
        raised_at=first.at,
        assigned_to=last.assigned_to,
        response=responded.text if responded else None,
        responded_at=responded.responded_at if responded else None,
        cleared_by=cleared.cleared_by if cleared else None,
        cleared_at=cleared.at if cleared else None,
        steps=rows,
    )


def get_note(session: Session, note_id: uuid.UUID) -> Note:
    rows = _rows(session, note_id)
    if not rows:
        raise NotFound(f"no review note {note_id}")
    return _assemble(rows)


def for_paper(session: Session, paper: Wp) -> list[Note]:
    rows = session.scalars(
        select(ReviewNote)
        .where(ReviewNote.wp_id == paper.id)
        .order_by(ReviewNote.note_id, ReviewNote.step)
    ).all()
    by_note: dict[uuid.UUID, list[ReviewNote]] = {}
    for row in rows:
        by_note.setdefault(row.note_id, []).append(row)
    notes = [_assemble(group) for group in by_note.values()]
    return sorted(notes, key=lambda n: n.raised_at)


def open_for_paper(session: Session, paper: Wp) -> list[Note]:
    return [n for n in for_paper(session, paper) if n.open]


def open_count(session: Session, paper: Wp) -> int:
    """Notes whose latest step is not 'cleared'. The gate spec 8.2 and 8.3 rely on."""
    latest = (
        select(ReviewNote.note_id, func.max(ReviewNote.step).label("step"))
        .where(ReviewNote.wp_id == paper.id)
        .group_by(ReviewNote.note_id)
        .subquery()
    )
    return (
        session.scalar(
            select(func.count())
            .select_from(ReviewNote)
            .join(
                latest,
                (ReviewNote.note_id == latest.c.note_id) & (ReviewNote.step == latest.c.step),
            )
            .where(ReviewNote.state != NoteState.CLEARED)
        )
        or 0
    )


def for_binder(session: Session, binder_id: uuid.UUID) -> list[tuple[Wp, Note]]:
    papers = session.scalars(select(Wp).where(Wp.binder_id == binder_id).order_by(Wp.ref)).all()
    return [(paper, note) for paper in papers for note in for_paper(session, paper)]


# --- the four steps ---------------------------------------------------------------------------


def raise_note(session: Session, paper: Wp, *, text: str, user: str, now: datetime) -> Note:
    body = (text or "").strip()
    if not body:
        raise Invalid("a review note needs text")
    note_id = uuid.uuid4()
    session.add(
        ReviewNote(
            note_id=note_id,
            step=1,
            wp_id=paper.id,
            state=NoteState.RAISED,
            text=body,
            raised_by=user,
            actor=user,
            at=now,
        )
    )
    session.flush()
    return get_note(session, note_id)


def _advance(
    session: Session, note: Note, to: NoteState, user: str, now: datetime, **fields: object
) -> Note:
    current = NoteState(note.state)
    if NEXT.get(current) != to:
        chain = " -> ".join(s.value for s in NoteState)
        raise Conflict(f"review note is {current.value}; it cannot be {to.value} now ({chain})")
    last = note.steps[-1]
    session.add(
        ReviewNote(
            note_id=note.note_id,
            step=last.step + 1,
            wp_id=note.wp_id,
            state=to,
            raised_by=note.raised_by,
            assigned_to=fields.get("assigned_to", last.assigned_to),
            text=fields.get("text"),
            responded_at=fields.get("responded_at"),
            cleared_by=fields.get("cleared_by"),
            actor=user,
            at=now,
        )
    )
    session.flush()
    return get_note(session, note.note_id)


def assign(session: Session, note: Note, *, assigned_to: str, user: str, now: datetime) -> Note:
    assignee = (assigned_to or "").strip()
    if not assignee:
        raise Invalid("assign the note to someone")
    return _advance(session, note, NoteState.ASSIGNED, user, now, assigned_to=assignee)


def respond(session: Session, note: Note, *, text: str, user: str, now: datetime) -> Note:
    body = (text or "").strip()
    if not body:
        raise Invalid("a response needs text")
    return _advance(session, note, NoteState.RESPONDED, user, now, text=body, responded_at=now)


def clear(session: Session, note: Note, *, user: str, now: datetime) -> Note:
    return _advance(session, note, NoteState.CLEARED, user, now, cleared_by=user)
