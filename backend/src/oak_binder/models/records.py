"""The discussions and departures logs (spec 2, 3H, 4; Pass 2 Stage A, D28).

Spec 4 names the records exactly:

    discussion   binder · date · participants[] · matter · outcome
    departure    binder · requirement · reason · alternative_procedure · approved_by

Both are append-only at the database, like wp_version. Each row also says who recorded it
and when (``recorded_by``, ``recorded_at``), as every append-only record here does. Nothing
else is added: "including TCWG" (spec 2, 3H) is met by the participants list itself, with a
role written after the name, for example "R. Mehta (TCWG, Audit Committee Chair)".
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base


class Discussion(Base):
    __tablename__ = "discussion"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    binder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("binder.id", name="fk_discussion_binder", ondelete="RESTRICT"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    participants: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    matter: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("cardinality(participants) >= 1", name="ck_discussion_has_participants"),
        CheckConstraint("btrim(matter) <> ''", name="ck_discussion_matter_not_blank"),
        CheckConstraint("btrim(recorded_by) <> ''", name="ck_discussion_recorded_by_not_blank"),
    )


class Departure(Base):
    __tablename__ = "departure"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    binder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("binder.id", name="fk_departure_binder", ondelete="RESTRICT"),
        nullable=False,
    )
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    alternative_procedure: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("btrim(requirement) <> ''", name="ck_departure_requirement_not_blank"),
        CheckConstraint("btrim(reason) <> ''", name="ck_departure_reason_not_blank"),
        CheckConstraint(
            "btrim(alternative_procedure) <> ''", name="ck_departure_alternative_not_blank"
        ),
        CheckConstraint("btrim(recorded_by) <> ''", name="ck_departure_recorded_by_not_blank"),
    )
