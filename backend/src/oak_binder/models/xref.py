"""Cross-references (spec 3B, 3E, 4; D26): ``xref · from_wp · to_wp | to_fs_line |
to_vault_doc · direction``.

A row is written on one paper (``from_wp``) and names exactly one target: another paper in
the same binder, a financial-statement line of the Spine (free text until the Spine exists),
or a document by its store id. ``direction`` says which way the reference reads: ``to``, this
paper refers to the target; ``from``, the target refers to this paper. A paper's references
"in and out" (spec 3B) are read from both ends, so a paper-to-paper link appears on both.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base


class Direction(enum.StrEnum):
    TO = "to"  # from_wp refers to the target
    FROM = "from"  # the target refers to from_wp


ONE_TARGET_SQL = (
    "(CASE WHEN to_wp IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN to_fs_line IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN to_vault_doc IS NOT NULL THEN 1 ELSE 0 END) = 1"
)


class Xref(Base):
    __tablename__ = "xref"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    from_wp: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp.id", name="fk_xref_from_wp", ondelete="RESTRICT"), nullable=False
    )
    to_wp: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wp.id", name="fk_xref_to_wp", ondelete="RESTRICT")
    )
    to_fs_line: Mapped[str | None] = mapped_column(Text)
    to_vault_doc: Mapped[str | None] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Completion work (D36, migration 0010): spec 3E makes a reference to a superseded paper
    # a blocker.
    # A paper target amended after the reference was made blocks until a person confirms the
    # reference against the target's current version; who, when and which version are kept.
    confirmed_by: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_version: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(ONE_TARGET_SQL, name="ck_xref_one_target"),
        CheckConstraint("to_wp IS NULL OR to_wp <> from_wp", name="ck_xref_not_self"),
        CheckConstraint(
            "to_fs_line IS NULL OR btrim(to_fs_line) <> ''", name="ck_xref_fs_line_not_blank"
        ),
        CheckConstraint(
            "to_vault_doc IS NULL OR btrim(to_vault_doc) <> ''",
            name="ck_xref_vault_doc_not_blank",
        ),
        CheckConstraint("direction IN ('to', 'from')", name="ck_xref_direction"),
        CheckConstraint("btrim(created_by) <> ''", name="ck_xref_created_by_not_blank"),
        CheckConstraint(
            "(confirmed_by IS NULL AND confirmed_at IS NULL AND confirmed_version IS NULL) OR "
            "(confirmed_by IS NOT NULL AND btrim(confirmed_by) <> '' AND confirmed_at IS NOT NULL "
            "AND confirmed_version IS NOT NULL AND confirmed_version >= 1)",
            name="ck_xref_confirmation_complete",
        ),
    )
