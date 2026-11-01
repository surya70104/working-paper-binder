"""Provenance of a paper a module generated (spec 3C, 8.8; Pass 2 Stage D, D31).

Spec 3C: "A paper produced by a module arrives complete, with its inputs and its citations,
and nobody retypes anything." The paper itself is an ordinary ``wp`` row; this table records
where it came from: the source, the module and its run, when it was generated, who delivered
it and when, the whole provenance block exactly as received (``payload``), and the content
hash of the module's fields at intake, so a later change to them is detectable for ever.

Append-only at the database, like every record table here (migration 0008). One row per
intake: regenerating a paper (Stage E) adds a row, so the history stays whole. Every version
body of a generated paper embeds the latest row (``services.papers.snapshot``), so the
version's content hash covers the inputs and citations and the archive carries them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base
from oak_binder.models.enums import SHA256_HEX_SQL, sql_list

# Spec 3C's five sources, in its order.
SOURCES: tuple[str, ...] = ("materiality", "sampling", "analytical_review", "workmind", "spine")

# Decision 5 (Stage D): how the memo's Spine figures were checked.
SPINE_FIGURES_CHECKS: tuple[str, ...] = ("verified", "not_checked")

# The fields a module generates and the Binder locks (decision 3): "nobody retypes anything"
# (spec 3C). The reference is stable anyway (spec 3B); the conclusion stays a person's to
# write (spec 7), so it is not here.
LOCKED_FIELDS: tuple[str, ...] = (
    "title",
    "section",
    "sa_refs",
    "objective",
    "procedure",
    "population_sample",
    "result",
)

# A paper the Financial Spine produced (Stage E, D32) carries figures, not narrative: the
# Spine never wrote its objective or procedure, so those stay a person's to write and are
# not locked (Stage E decision 5).
SPINE_LOCKED_FIELDS: tuple[str, ...] = (
    "title",
    "section",
    "sa_refs",
    "population_sample",
    "result",
)


def locked_fields_for(source: str) -> tuple[str, ...]:
    return SPINE_LOCKED_FIELDS if source == "spine" else LOCKED_FIELDS


class WpGeneration(Base):
    __tablename__ = "wp_generation"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp.id", name="fk_wp_generation_wp", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str] = mapped_column(Text, nullable=False)
    module_version: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_by: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash_at_intake: Mapped[str] = mapped_column(Text, nullable=False)
    spine_figures: Mapped[str | None] = mapped_column(Text)
    # Completion work (D37, migration 0010): how the delivery's run was verified at intake (the
    # WorkMind run read back: status, who accepted it, when, the endpoint read); None when
    # the source needs no read-back.
    run_verification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint(f"source IN ({sql_list(SOURCES)})", name="ck_wp_generation_source"),
        CheckConstraint("btrim(module) <> ''", name="ck_wp_generation_module_not_blank"),
        CheckConstraint(
            "run_id IS NULL OR btrim(run_id) <> ''", name="ck_wp_generation_run_id_not_blank"
        ),
        CheckConstraint("btrim(received_by) <> ''", name="ck_wp_generation_received_by_not_blank"),
        CheckConstraint(
            f"content_hash_at_intake {SHA256_HEX_SQL}", name="ck_wp_generation_content_hash"
        ),
        CheckConstraint(
            f"spine_figures IS NULL OR spine_figures IN ({sql_list(SPINE_FIGURES_CHECKS)})",
            name="ck_wp_generation_spine_figures",
        ),
        Index(
            "uq_wp_generation_source_run",
            "source",
            "run_id",
            unique=True,
            postgresql_where=text("run_id IS NOT NULL"),
        ),
    )
