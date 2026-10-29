"""Review notes (spec 3D, 4, 8.2): raised -> assigned -> responded -> cleared.

The table is append-only (spec 4), so a note's life is a sequence of rows sharing one
``note_id``, one row per step, exactly as wp_version records sign-offs. The latest row by
``step`` is the note's current state. The spec's fields are all here: wp, raised_by,
assigned_to, text, state, responded_at, cleared_by; ``actor`` and ``at`` say who wrote each
step and when.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base
from oak_binder.models.enums import sql_list


class NoteState(StrEnum):
    RAISED = "raised"
    ASSIGNED = "assigned"
    RESPONDED = "responded"
    CLEARED = "cleared"


class ReviewNote(Base):
    __tablename__ = "review_note"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    note_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp.id", name="fk_review_note_wp", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    raised_by: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleared_by: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("note_id", "step", name="uq_review_note_note_step"),
        CheckConstraint("step >= 1", name="ck_review_note_step_positive"),
        CheckConstraint(f"state IN ({sql_list(NoteState)})", name="ck_review_note_state"),
        CheckConstraint("btrim(raised_by) <> ''", name="ck_review_note_raised_by_not_blank"),
        CheckConstraint("btrim(actor) <> ''", name="ck_review_note_actor_not_blank"),
        # Each state carries the field the spec gives it, and only then.
        CheckConstraint(
            "state <> 'raised' OR (text IS NOT NULL AND btrim(text) <> '')",
            name="ck_review_note_raised_has_text",
        ),
        CheckConstraint(
            "state <> 'assigned' OR assigned_to IS NOT NULL",
            name="ck_review_note_assigned_has_assignee",
        ),
        CheckConstraint(
            "(state = 'responded') = (responded_at IS NOT NULL)",
            name="ck_review_note_responded_at",
        ),
        CheckConstraint(
            "(state = 'cleared') = (cleared_by IS NOT NULL)", name="ck_review_note_cleared_by"
        ),
    )
