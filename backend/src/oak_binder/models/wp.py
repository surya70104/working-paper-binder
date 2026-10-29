"""The working paper, its immutable versions and their attachments (spec 3B, 4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from oak_binder.db import Base
from oak_binder.models.enums import SECTIONS, SHA256_HEX_SQL, WpStatus, sql_list

# Spec 2 and 8.1: a paper missing a conclusion cannot be signed off.
SIGNED_OFF_NEEDS_CONCLUSION_SQL = (
    f"status <> '{WpStatus.SIGNED_OFF}' OR (conclusion IS NOT NULL AND btrim(conclusion) <> '')"
)


class Wp(Base):
    """The live working paper. Its content fields are the current state; every sign-off
    snapshots them into a wp_version row, which never changes."""

    __tablename__ = "wp"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    binder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("binder.id", name="fk_wp_binder", ondelete="RESTRICT"), nullable=False
    )
    ref: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    sa_refs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    objective: Mapped[str | None] = mapped_column(Text)
    procedure: Mapped[str | None] = mapped_column(Text)
    population_sample: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=WpStatus.DRAFT)
    current_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("binder_id", "ref", name="uq_wp_binder_ref"),
        CheckConstraint("btrim(ref) <> ''", name="ck_wp_ref_not_blank"),
        CheckConstraint(f"section IN ({sql_list(SECTIONS)})", name="ck_wp_section"),
        CheckConstraint(f"status IN ({sql_list(WpStatus)})", name="ck_wp_status"),
        CheckConstraint(SIGNED_OFF_NEEDS_CONCLUSION_SQL, name="ck_wp_signed_off_has_conclusion"),
        CheckConstraint(
            "current_version IS NULL OR current_version >= 1", name="ck_wp_current_version"
        ),
        # Any status past draft is the result of a sign-off, so it must point at a version.
        CheckConstraint(
            f"status = '{WpStatus.DRAFT}' OR current_version IS NOT NULL",
            name="ck_wp_status_needs_version",
        ),
        # current_version must be a real version of this paper. The two tables reference each
        # other, so this key is added after both exist (use_alter).
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["wp_version.wp_id", "wp_version.version"],
            name="fk_wp_current_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )


class WpVersion(Base):
    """An immutable snapshot of a paper at a sign-off. Append-only: the database refuses
    UPDATE, DELETE and TRUNCATE (migration 0001, architecture D6)."""

    __tablename__ = "wp_version"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp.id", name="fk_wp_version_wp", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prepared_by: Mapped[str] = mapped_column(Text, nullable=False)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The final sign-off (reviewed -> signed off) has its own actor and time (spec 3D, 8.9).
    signed_off_by: Mapped[str | None] = mapped_column(Text)
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    amendment_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("wp_id", "version", name="uq_wp_version_wp_version"),
        CheckConstraint("version >= 1", name="ck_wp_version_positive"),
        CheckConstraint("btrim(prepared_by) <> ''", name="ck_wp_version_prepared_by_not_blank"),
        CheckConstraint(
            "(reviewed_by IS NULL) = (reviewed_at IS NULL)", name="ck_wp_version_review_pair"
        ),
        CheckConstraint(
            "(signed_off_by IS NULL) = (signed_off_at IS NULL)",
            name="ck_wp_version_sign_off_pair",
        ),
        # A sign-off presupposes a review: the chain is prepared -> reviewed -> signed off.
        CheckConstraint(
            "signed_off_by IS NULL OR reviewed_by IS NOT NULL",
            name="ck_wp_version_sign_off_needs_review",
        ),
        CheckConstraint(f"content_hash {SHA256_HEX_SQL}", name="ck_wp_version_content_hash"),
    )


class WpAttachment(Base):
    """A native-format file attached to a working paper (spec 3B, 3G), stored by its SHA-256.

    An attachment belongs to the paper from the moment it is uploaded (D17), which may be
    before the paper has any version. ``wp_version_id`` is set at the next prepare: the
    version at which the file first became part of the signed record. Every version body
    lists the paper's attachments, so the content hash covers the evidence.
    ``vault_doc_id`` holds the local store's key, the file's SHA-256; there is no vault yet.
    """

    __tablename__ = "wp_attachment"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp.id", name="fk_wp_attachment_wp", ondelete="RESTRICT"), nullable=False
    )
    wp_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wp_version.id", name="fk_wp_attachment_wp_version", ondelete="RESTRICT")
    )
    vault_doc_id: Mapped[str] = mapped_column(Text, nullable=False)
    identifying_chars: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    attached_by: Mapped[str] = mapped_column(Text, nullable=False)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("wp_id", "sha256", name="uq_wp_attachment_wp_sha256"),
        CheckConstraint(f"sha256 {SHA256_HEX_SQL}", name="ck_wp_attachment_sha256"),
        CheckConstraint("btrim(filename) <> ''", name="ck_wp_attachment_filename_not_blank"),
        CheckConstraint("size_bytes >= 0", name="ck_wp_attachment_size"),
    )
