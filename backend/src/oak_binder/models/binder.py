"""The binder: one audit file per engagement (spec 4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base
from oak_binder.models.enums import BinderState, Template, sql_list

# Spec 3F and 3G: assembly deadline = report date + 60 days; retention = report date + 7 years.
# Enforced by the database so the two clocks can never disagree with the report date.
# Every column is tested IS NOT NULL explicitly: in SQL a comparison with NULL is "unknown",
# and a CHECK constraint lets "unknown" through, so "assembly_due = report_date + 60" alone
# would accept a missing assembly_due.
REPORT_CLOCKS_SQL = (
    "(report_date IS NULL AND assembly_due IS NULL AND retention_until IS NULL) OR "
    "(report_date IS NOT NULL AND assembly_due IS NOT NULL AND retention_until IS NOT NULL AND "
    "assembly_due = report_date + 60 AND "
    "retention_until = (report_date + INTERVAL '7 years')::date)"
)

# Spec 3F: Assemble freezes the file and computes a file hash. The state, the timestamp and
# the hash move together, and a file cannot be assembled before its report is dated. A purged
# binder keeps its assembly record (spec 3G: the purge writes its own record; D18).
# assembly_hash IS NOT NULL is explicit for the same reason: NULL ~ pattern is "unknown".
ASSEMBLY_SQL = (
    "(state = 'open' AND assembled_at IS NULL AND assembly_hash IS NULL) OR "
    "(state IN ('assembled', 'purged') AND report_date IS NOT NULL AND "
    "assembled_at IS NOT NULL AND assembly_hash IS NOT NULL AND "
    "assembly_hash ~ '^[0-9a-f]{64}$')"
)


class Binder(Base):
    __tablename__ = "binder"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    engagement: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    report_date: Mapped[date | None] = mapped_column(Date)
    assembly_due: Mapped[date | None] = mapped_column(Date)
    assembled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assembly_hash: Mapped[str | None] = mapped_column(Text)
    retention_until: Mapped[date | None] = mapped_column(Date)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=BinderState.OPEN)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("engagement", name="uq_binder_engagement"),
        CheckConstraint("btrim(engagement) <> ''", name="ck_binder_engagement_not_blank"),
        CheckConstraint(f"template IN ({sql_list(Template)})", name="ck_binder_template"),
        CheckConstraint(f"state IN ({sql_list(BinderState)})", name="ck_binder_state"),
        CheckConstraint(REPORT_CLOCKS_SQL, name="ck_binder_report_clocks"),
        CheckConstraint(ASSEMBLY_SQL, name="ck_binder_assembly"),
    )
