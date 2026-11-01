"""Working papers: creation, editing, the immutable version history and the sign-off
workflow (spec 3B, 3D, 8.1, 8.2, 8.9; architecture D9, D12, D14).

Status chain: draft -> prepared -> in_review -> reviewed -> signed_off.
  prepare   draft      -> prepared    writes version N   (prepared_by, prepared_at)
  submit    prepared   -> in_review   no version
  review    in_review  -> reviewed    writes version N+1 (preparer copied, reviewed_by/at)
  sign_off  reviewed   -> signed_off  writes version N+2 (both copied, signed_off_by/at)
Any content edit returns the paper to draft: the sign-offs on file refer to earlier
versions, which stay in wp_version untouched.

Every version is inserted and flushed before the paper's status and current_version move,
so the database rules "a non-draft status needs a version" and "current_version is a real
version" hold at every statement.

After assembly the chain still runs, because an amended paper must be signed off again
before the file is re-assembled; only ordinary edits are refused (spec 3F, D17).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from oak_binder.errors import Conflict, Invalid, NotFound
from oak_binder.hashing import content_hash
from oak_binder.models import (
    SECTIONS,
    Binder,
    BinderState,
    Wp,
    WpAttachment,
    WpGeneration,
    WpStatus,
    WpVersion,
)
from oak_binder.models.generation import LOCKED_FIELDS, locked_fields_for
from oak_binder.services.binders import require_open

CONTENT_FIELDS: tuple[str, ...] = (
    "ref",
    "section",
    "title",
    "sa_refs",
    "objective",
    "procedure",
    "population_sample",
    "result",
    "conclusion",
)
EDITABLE_FIELDS: tuple[str, ...] = tuple(f for f in CONTENT_FIELDS if f != "ref")


def snapshot(session: Session, paper: Wp) -> dict[str, Any]:
    """The body stored in a version: the paper's content fields plus its attachments by
    hash, so the content hash covers the evidence (spec 2, 3G)."""
    body: dict[str, Any] = {name: getattr(paper, name) for name in CONTENT_FIELDS}
    body["sa_refs"] = list(paper.sa_refs)
    rows = session.scalars(
        select(WpAttachment).where(WpAttachment.wp_id == paper.id).order_by(WpAttachment.sha256)
    ).all()
    body["attachments"] = [
        {
            "sha256": a.sha256,
            "filename": a.filename,
            "size_bytes": a.size_bytes,
            "identifying_chars": a.identifying_chars,
        }
        for a in rows
    ]
    generation = latest_generation(session, paper)
    if generation is not None:
        # A generated paper's provenance travels in every version (spec 3C; D31), so the
        # content hash covers the inputs and citations. Hand-made papers gain no key.
        body["generated"] = provenance_block(generation)
    return body


# --- generated papers (spec 3C; Pass 2 Stage D, D31) -----------------------------------------


def latest_generation(session: Session, paper: Wp) -> WpGeneration | None:
    """The most recent intake record of a generated paper, or None for a hand-made one."""
    return session.scalars(
        select(WpGeneration)
        .where(WpGeneration.wp_id == paper.id)
        .order_by(WpGeneration.received_at.desc(), WpGeneration.id.desc())
        .limit(1)
    ).first()


def provenance_block(row: WpGeneration) -> dict[str, Any]:
    """The provenance as it is embedded in a version body: who generated and delivered the
    paper and when, the module's fields' hash at intake, the Spine-figures check, and the
    whole block as received (inputs, citations and the source block)."""
    return {
        "source": row.source,
        "module": row.module,
        "module_version": row.module_version,
        "run_id": row.run_id,
        "generated_at": row.generated_at.isoformat(),
        "received_by": row.received_by,
        "received_at": row.received_at.isoformat(),
        "content_hash_at_intake": row.content_hash_at_intake,
        "spine_figures_check": row.spine_figures,
        "payload": dict(row.payload),
    }


def refuse_locked(session: Session, paper: Wp, changes: Mapping[str, Any]) -> None:
    """A generated paper's module fields are not retyped here (spec 3C; decision 3): a change
    to one is refused and the module is named. The conclusion stays a person's (spec 7)."""
    if not any(name in changes for name in LOCKED_FIELDS):
        return
    generation = latest_generation(session, paper)
    if generation is None:
        return
    touched = [name for name in locked_fields_for(generation.source) if name in changes]
    if not touched:
        return
    raise Invalid(
        f"{', '.join(touched)} of {paper.ref} came from {generation.module} "
        f"({generation.source}) and is not retyped here (spec 3C); regenerate the paper "
        "from the module. The conclusion may be written."
    )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validate_content(values: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for name, value in values.items():
        if name not in CONTENT_FIELDS:
            raise Invalid(f"unknown field {name!r}")
        if name == "sa_refs":
            refs = [str(v).strip() for v in (value or [])]
            cleaned[name] = [r for r in refs if r]
        elif name == "section":
            section = str(value).strip().upper()
            if section not in SECTIONS:
                raise Invalid(f"section must be one of {''.join(SECTIONS)}, not {value!r}")
            cleaned[name] = section
        elif name in ("ref", "title"):
            text = _clean_text(value)
            if not text:
                raise Invalid(f"{name} must not be blank")
            cleaned[name] = text
        else:
            cleaned[name] = _clean_text(value)
    return cleaned


def apply_changes(paper: Wp, cleaned: Mapping[str, Any]) -> bool:
    """Set the cleaned fields on the paper; True if anything actually changed."""
    changed = False
    for name, value in cleaned.items():
        if getattr(paper, name) != value:
            setattr(paper, name, value)
            changed = True
    return changed


def create_paper(session: Session, binder: Binder, values: Mapping[str, Any]) -> Wp:
    require_open(binder)
    cleaned = validate_content(values)
    for name in ("ref", "section", "title"):
        if name not in cleaned:
            raise Invalid(f"{name} is required")
    paper = Wp(binder_id=binder.id, status=WpStatus.DRAFT, **cleaned)
    session.add(paper)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if "uq_wp_binder_ref" in str(exc):
            raise Conflict(
                f"reference {cleaned['ref']!r} is already used in this binder; "
                "references are stable and never reused (spec 3B)"
            ) from exc
        raise
    return paper


def get_paper(session: Session, paper_id: uuid.UUID) -> Wp:
    paper = session.get(Wp, paper_id)
    if paper is None:
        raise NotFound(f"no working paper {paper_id}")
    return paper


def update_paper(session: Session, paper: Wp, changes: Mapping[str, Any]) -> Wp:
    """Edit content fields on an open binder. The reference is immutable. Any real change
    returns the paper to draft; its earlier versions stay on file. On an assembled binder
    use services.assembly.amend, which records the reason (spec 3F)."""
    if "ref" in changes:
        raise Invalid("the reference is stable and cannot be changed (spec 3B)")
    require_open(binder_of(session, paper))
    refuse_locked(session, paper, changes)
    cleaned = validate_content(changes)
    if apply_changes(paper, cleaned) and paper.status != WpStatus.DRAFT:
        paper.status = WpStatus.DRAFT
    session.flush()
    return paper


def versions(session: Session, paper: Wp) -> list[WpVersion]:
    return list(
        session.scalars(
            select(WpVersion).where(WpVersion.wp_id == paper.id).order_by(WpVersion.version)
        ).all()
    )


def current_version(session: Session, paper: Wp) -> WpVersion | None:
    if paper.current_version is None:
        return None
    return session.scalars(
        select(WpVersion).where(
            WpVersion.wp_id == paper.id, WpVersion.version == paper.current_version
        )
    ).one()


# --- the workflow -----------------------------------------------------------------------------


def require_not_purged(binder: Binder) -> None:
    if binder.state == BinderState.PURGED:
        raise Conflict(
            f"binder for {binder.engagement!r} has been purged after retention; "
            "its content is gone and nothing can be signed off"
        )


def _expect_status(paper: Wp, *allowed: WpStatus, action: str) -> None:
    if paper.status not in allowed:
        wanted = " or ".join(s.value for s in allowed)
        raise Conflict(
            f"cannot {action} paper {paper.ref}: its status is {paper.status}, not {wanted}"
        )


def next_version_number(session: Session, paper: Wp) -> int:
    existing = versions(session, paper)
    return (existing[-1].version + 1) if existing else 1


def append_version(session: Session, paper: Wp, version: WpVersion, status: WpStatus) -> None:
    """Insert the version, then move the paper to it. Two flushes on purpose: the row must
    exist before current_version can point at it. A concurrent sign-off on the same paper
    collides on (wp_id, version) and is reported as a conflict, not a server error."""
    session.add(version)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if "uq_wp_version_wp_version" in str(exc):
            raise Conflict(
                f"paper {paper.ref} was signed off by another request at the same time; "
                "reload it and try again"
            ) from exc
        raise
    paper.status = status
    paper.current_version = version.version
    session.flush()


def prepare(session: Session, paper: Wp, user: str, now: datetime) -> WpVersion:
    """The preparer's sign-off: draft -> prepared, writing an immutable version. Attachments
    not yet part of a signed version join this one."""
    from oak_binder.services.attachments import link_to_version

    require_not_purged(binder_of(session, paper))
    _expect_status(paper, WpStatus.DRAFT, action="prepare")
    body = snapshot(session, paper)
    version = WpVersion(
        wp_id=paper.id,
        version=next_version_number(session, paper),
        body=body,
        prepared_by=user,
        prepared_at=now,
        content_hash=content_hash(body),
    )
    append_version(session, paper, version, WpStatus.PREPARED)
    link_to_version(session, paper, version.id)
    return version


def submit_for_review(session: Session, paper: Wp) -> Wp:
    require_not_purged(binder_of(session, paper))
    _expect_status(paper, WpStatus.PREPARED, action="submit for review")
    paper.status = WpStatus.IN_REVIEW
    session.flush()
    return paper


def review(session: Session, paper: Wp, user: str, now: datetime) -> WpVersion | None:
    """The reviewer's sign-off: in_review -> reviewed, writing a version that carries both
    the preparer (copied from the prepared version) and the reviewer.

    With review levels configured on the binder (spec 3D; Stage F, D33) each call records
    the next level's review of the prepared version, by ``user``, as an append-only row; the
    paper stays in review and None is returned until the last configured level, whose
    reviewer is the one the reviewed version names."""
    from oak_binder.services import review_levels

    binder = binder_of(session, paper)
    require_not_purged(binder)
    _expect_status(paper, WpStatus.IN_REVIEW, action="review")
    prepared = current_version(session, paper)
    if prepared is None:
        raise Conflict(f"paper {paper.ref} has no prepared version to review")
    body = snapshot(session, paper)
    if content_hash(body) != prepared.content_hash:
        raise Conflict(
            f"paper {paper.ref} changed since version {prepared.version} was prepared; "
            "it must be prepared again"
        )
    if review_levels.levels_of(binder):
        _row, completed = review_levels.record_level_review(
            session, binder, paper, prepared, user, now
        )
        if not completed:
            return None
    version = WpVersion(
        wp_id=paper.id,
        version=next_version_number(session, paper),
        body=body,
        prepared_by=prepared.prepared_by,
        prepared_at=prepared.prepared_at,
        reviewed_by=user,
        reviewed_at=now,
        content_hash=prepared.content_hash,
    )
    append_version(session, paper, version, WpStatus.REVIEWED)
    return version


def open_review_notes(session: Session, paper: Wp) -> int:
    """Spec 3D and 8.2: a paper with an open review note cannot be signed off. A note is
    open until its latest step is 'cleared' (services.review_notes)."""
    from oak_binder.services.review_notes import open_count

    return open_count(session, paper)


def sign_off(session: Session, paper: Wp, user: str, now: datetime) -> WpVersion:
    """The final sign-off: reviewed -> signed_off, writing a version that carries the
    preparer, the reviewer and the signer, so who, when and which version (spec 8.9) are one
    immutable row."""
    require_not_purged(binder_of(session, paper))
    _expect_status(paper, WpStatus.REVIEWED, action="sign off")
    if not (paper.conclusion and paper.conclusion.strip()):
        raise Invalid(f"paper {paper.ref} has no conclusion and cannot be signed off (spec 8.1)")
    notes = open_review_notes(session, paper)
    if notes:
        raise Conflict(f"paper {paper.ref} has {notes} open review note(s) (spec 8.2)")
    reviewed = current_version(session, paper)
    if reviewed is None or reviewed.reviewed_by is None:
        raise Conflict(f"paper {paper.ref} has no reviewed version to sign off")
    body = snapshot(session, paper)
    if content_hash(body) != reviewed.content_hash:
        raise Conflict(
            f"paper {paper.ref} changed since version {reviewed.version} was reviewed; "
            "it must be prepared again"
        )
    version = WpVersion(
        wp_id=paper.id,
        version=next_version_number(session, paper),
        body=body,
        prepared_by=reviewed.prepared_by,
        prepared_at=reviewed.prepared_at,
        reviewed_by=reviewed.reviewed_by,
        reviewed_at=reviewed.reviewed_at,
        signed_off_by=user,
        signed_off_at=now,
        content_hash=reviewed.content_hash,
    )
    append_version(session, paper, version, WpStatus.SIGNED_OFF)
    return version


def binder_of(session: Session, paper: Wp) -> Binder:
    binder = session.get(Binder, paper.binder_id)
    assert binder is not None  # the foreign key guarantees it  # noqa: S101
    return binder
