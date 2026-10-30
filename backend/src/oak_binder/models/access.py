"""Access log (spec 3H, 4): who opened the file after assembly. Append-only, post-assembly
only. The spec's record is ``access_log · binder · user · action · at``; ``action`` says what
was opened: the binder, a paper, an attachment, the assembly status, a verification, a
production."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base


class AccessLog(Base):
    __tablename__ = "access_log"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    binder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("binder.id", name="fk_access_log_binder", ondelete="RESTRICT"),
        nullable=False,
    )
    user: Mapped[str] = mapped_column("user", Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("btrim(\"user\") <> ''", name="ck_access_log_user_not_blank"),
        CheckConstraint("btrim(action) <> ''", name="ck_access_log_action_not_blank"),
    )
