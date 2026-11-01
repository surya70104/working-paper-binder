"""A level review (spec 3D "Levels: preparer → senior → manager → partner → EQR, configurable
per engagement"; Pass 2 Stage F, D33).

One row per review at one configured level of one prepared version: who reviewed, when, at
which level, and which version. Append-only at the database (migration 0009), like every
record here. The preparer is not a row: the prepared ``wp_version`` already records the
preparer's identity, time and version (spec 3B, 8.9), and is presented as level one. When the
last configured level is reviewed the ordinary ``reviewed`` version row is written with that
reviewer in ``reviewed_by``; the sign-off step is unchanged.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base


class WpReview(Base):
    __tablename__ = "wp_review"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp.id", name="fk_wp_review_wp", ondelete="RESTRICT"), nullable=False
    )
    wp_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp_version.id", name="fk_wp_review_wp_version", ondelete="RESTRICT"),
        nullable=False,
    )
    level: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("wp_version_id", "level", name="uq_wp_review_version_level"),
        CheckConstraint("btrim(level) <> ''", name="ck_wp_review_level_not_blank"),
        CheckConstraint("btrim(reviewer) <> ''", name="ck_wp_review_reviewer_not_blank"),
    )
