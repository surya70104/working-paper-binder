"""What happened to a binder after it left ordinary editing: assembled, amended, purged,
produced (spec 3F, 3G). Append-only at the database, like wp_version (D6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base
from oak_binder.models.enums import EventKind, sql_list


class BinderEvent(Base):
    __tablename__ = "binder_event"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    binder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("binder.id", name="fk_binder_event_binder", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        CheckConstraint(f"kind IN ({sql_list(EventKind)})", name="ck_binder_event_kind"),
        CheckConstraint("btrim(actor) <> ''", name="ck_binder_event_actor_not_blank"),
    )
