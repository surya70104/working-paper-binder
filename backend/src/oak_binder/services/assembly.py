"""Assembly: the blockers, the Assemble action, the manifest and its file hash, verification,
and post-assembly amendments (spec 3F, 8.3, 8.4, 8.5; D17).

The manifest is a plain JSON document built from the database alone: the binder, then every
paper in reference order with its current version, that version's content hash and its
attachments by hash. The file hash is the SHA-256 of the canonical JSON of the manifest, so
anyone holding the database can recompute it (spec 8.5). The manifest is stored with the
event that produced it, in the append-only binder_event table.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from oak_binder import __version__
from oak_binder.errors import Conflict, Invalid, NotFound, SpineUnavailable
from oak_binder.hashing import content_hash
from oak_binder.models import (
    Binder,
    BinderEvent,
    BinderState,
    Departure,
    Discussion,
    EventKind,
    Wp,
    WpAttachment,
    WpStatus,
    WpVersion,
)
from oak_binder.services import fs_lines as fs_line_service
from oak_binder.services import papers as paper_service
from oak_binder.services import xrefs as xref_service
from oak_binder.services.attachments import AttachmentStore, _attach_row, verified_read
from oak_binder.services.binders import build_index
from oak_binder.services.spine_client import SpineClient, SpineVersion

MANIFEST_VERSION = 1

# Spec 3F names four blockers. Three are checked in full; broken cross-references are
# checked for paper and document targets (D26) and cannot be checked for Spine lines, since
# the Spine is not part of this product (D21). What is not checked is reported, never counted
# as clear.
NOT_CHECKED: tuple[str, ...] = (
    "cross-references to FS lines: the binder is not linked to a Financial Spine version "
    "(D29, D30), so a reference to an FS line cannot be followed; references to papers and "
    "documents are checked",
)


def not_checked(session: Session, binder: Binder, spine: SpineClient | None = None) -> list[str]:
    """What this binder's assembly cannot check. Empty once the binder is linked to a Spine
    version whose lines can be read: every reference is then checkable (D30). Otherwise the
    FS-line references, with their count and the reason."""
    from oak_binder.services import spine_papers  # late: spine_papers imports this module's peers

    # Stage E (D32, decision 8): a Spine paper built from another version than the one the
    # binder is linked to is information, never a blocker; it is said here, by name.
    notes = spine_papers.stale_notes(session, spine, binder)
    lines = fs_line_service.for_binder(spine, binder)
    if lines.available:
        return notes
    count = xref_service.unchecked_fs_lines(session, binder)
    suffix = f" ({count} such reference(s) in this file)" if count else " (none in this file)"
    if binder.spine_version_id is None:
        return [NOT_CHECKED[0] + suffix, *notes]
    return [
        f"cross-references to FS lines: {lines.reason}; references to papers and documents "
        f"are checked{suffix}",
        *notes,
    ]


@dataclass(frozen=True)
class Blocker:
    kind: str
    ref: str | None
    detail: str

    def __str__(self) -> str:
        where = f" {self.ref}" if self.ref else ""
        return f"{self.kind}{where}: {self.detail}"


def spine_blocker(
    spine: SpineClient | None, binder: Binder
) -> tuple[Blocker | None, SpineVersion | None]:
    """A linked Spine version must be locked before the file is assembled (D29): an unlocked
    version's figures and lines can still change under the file. A Spine that cannot be
    read is a named blocker too, never silently clear. A binder with no version linked has
    nothing to check."""
    if binder.spine_version_id is None:
        return None, None
    if spine is None:
        return (
            Blocker(
                "spine_version_not_verified",
                None,
                "the binder is linked to a Spine version but no Financial Spine is configured "
                "(OAK_SPINE_URL), so its lock cannot be confirmed",
            ),
            None,
        )
    try:
        version = spine.version(binder.spine_version_id)
    except NotFound as exc:
        return Blocker("spine_version_missing", None, str(exc)), None
    except SpineUnavailable as exc:
        return Blocker("spine_unreachable", None, str(exc)), None
    if not version.is_locked:
        return (
            Blocker(
                "spine_version_unlocked",
                None,
                f"Spine version {version.version_no or ''} {version.label!r} is not locked; "
                "lock it in the Spine, or link a locked version",
            ),
            version,
        )
    return None, version


def blockers(session: Session, binder: Binder, spine: SpineClient | None = None) -> list[Blocker]:
    """Spec 3F and 8.3: unsigned papers, open notes, broken references, missing required
    papers, each named. Plus the report date, without which there is no deadline, and a
    linked Spine version that is not locked (D29)."""
    found: list[Blocker] = []
    if binder.report_date is None:
        found.append(Blocker("report_not_dated", None, "the report date starts the 60-day clock"))
    index = build_index(session, binder)
    for section in index.sections:
        for required in section.missing:
            found.append(Blocker("missing_required_paper", required.ref, required.title))
        for paper in section.papers:
            if paper.status != WpStatus.SIGNED_OFF:
                found.append(Blocker("unsigned_paper", paper.ref, f"status is {paper.status}"))
            notes = paper_service.open_review_notes(session, paper)
            if notes:
                found.append(
                    Blocker("open_review_notes", paper.ref, f"{notes} open review note(s)")
                )
    for item in xref_service.broken(session, binder, fs_line_service.for_binder(spine, binder)):
        found.append(Blocker("broken_reference", item.from_ref, item.detail))
    spine_block, _ = spine_blocker(spine, binder)
    if spine_block is not None:
        found.append(spine_block)
    return found


def build_manifest(session: Session, binder: Binder) -> dict[str, Any]:
    """Deterministic: no timestamps, papers in reference order, attachments by hash."""
    papers = session.scalars(select(Wp).where(Wp.binder_id == binder.id).order_by(Wp.ref)).all()
    entries: list[dict[str, Any]] = []
    for paper in papers:
        version = paper_service.current_version(session, paper)
        attachments = session.scalars(
            select(WpAttachment).where(WpAttachment.wp_id == paper.id).order_by(WpAttachment.sha256)
        ).all()
        entries.append(
            {
                "ref": paper.ref,
                "wp_id": str(paper.id),
                "section": paper.section,
                "title": paper.title,
                "status": paper.status,
                "version": version.version if version else None,
                "content_hash": version.content_hash if version else None,
                "prepared_by": version.prepared_by if version else None,
                "reviewed_by": version.reviewed_by if version else None,
                "signed_off_by": version.signed_off_by if version else None,
                "attachments": [
                    {
                        "sha256": a.sha256,
                        "filename": a.filename,
                        "media_type": a.media_type,
                        "size_bytes": a.size_bytes,
                        "identifying_chars": a.identifying_chars,
                    }
                    for a in attachments
                ],
            }
        )
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "generator": f"oak-binder {__version__}",
        "binder": {
            "id": str(binder.id),
            "engagement": binder.engagement,
            "template": binder.template,
            "report_date": binder.report_date.isoformat() if binder.report_date else None,
            "assembly_due": binder.assembly_due.isoformat() if binder.assembly_due else None,
            "retention_until": (
                binder.retention_until.isoformat() if binder.retention_until else None
            ),
        },
        "papers": entries,
    }
    # The Spine link (spec 3A; D29), only when one exists, so files assembled without a
    # link keep the manifest and hash they recorded. The ids are the Binder's own record;
    # the version's hash at assembly is in the assembled event, read from the Spine then.
    if binder.spine_engagement_id is not None:
        manifest["spine"] = {
            "engagement_id": str(binder.spine_engagement_id),
            "version_id": (
                str(binder.spine_version_id) if binder.spine_version_id is not None else None
            ),
        }
    # The discussions and departures logs (spec 3H) are part of the frozen file. They are
    # listed only when any exist, so a file assembled before the logs existed keeps the
    # manifest and hash it recorded (D28).
    discussions = session.scalars(
        select(Discussion)
        .where(Discussion.binder_id == binder.id)
        .order_by(Discussion.date, Discussion.recorded_at, Discussion.id)
    ).all()
    if discussions:
        manifest["discussions"] = [
            {
                "id": str(d.id),
                "date": d.date.isoformat(),
                "participants": list(d.participants),
                "matter": d.matter,
                "outcome": d.outcome,
                "recorded_by": d.recorded_by,
                "recorded_at": d.recorded_at.isoformat(),
            }
            for d in discussions
        ]
    departures = session.scalars(
        select(Departure)
        .where(Departure.binder_id == binder.id)
        .order_by(Departure.recorded_at, Departure.id)
    ).all()
    if departures:
        manifest["departures"] = [
            {
                "id": str(d.id),
                "requirement": d.requirement,
                "reason": d.reason,
                "alternative_procedure": d.alternative_procedure,
                "approved_by": d.approved_by,
                "recorded_by": d.recorded_by,
                "recorded_at": d.recorded_at.isoformat(),
            }
            for d in departures
        ]
    return manifest


def file_hash(manifest: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical manifest JSON (spec 3F, 8.5)."""
    return content_hash(manifest)


def record(
    session: Session,
    binder: Binder,
    kind: EventKind,
    actor: str,
    at: datetime,
    *,
    reason: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> BinderEvent:
    event = BinderEvent(
        binder_id=binder.id,
        kind=kind,
        actor=actor,
        at=at,
        reason=reason,
        details=dict(details or {}),
    )
    session.add(event)
    session.flush()
    return event


def events(session: Session, binder: Binder) -> list[BinderEvent]:
    return list(
        session.scalars(
            select(BinderEvent)
            .where(BinderEvent.binder_id == binder.id)
            .order_by(BinderEvent.at, BinderEvent.id)
        ).all()
    )


def latest_manifest(session: Session, binder: Binder) -> dict[str, Any] | None:
    """The manifest recorded by the most recent assembly."""
    for event in reversed(events(session, binder)):
        if event.kind == EventKind.ASSEMBLED:
            manifest: dict[str, Any] = event.details["manifest"]
            return manifest
    return None


def assemble(
    session: Session,
    binder: Binder,
    user: str,
    now: datetime,
    spine: SpineClient | None = None,
) -> BinderEvent:
    """Freeze the file: refuse while anything blocks, else record the manifest and hash.
    On an already assembled binder this re-assembles after amendments; the previous hash is
    kept in the event so the chain of manifests is visible (spec 3F). A linked Spine
    version's lock hash is recorded in the event too (D29)."""
    if binder.state == BinderState.PURGED:
        raise Conflict(f"binder for {binder.engagement!r} has been purged")
    found = blockers(session, binder, spine)
    if found:
        listed = "; ".join(str(b) for b in found)
        raise Conflict(f"assembly is blocked by {len(found)} item(s): {listed}")
    manifest = build_manifest(session, binder)
    digest = file_hash(manifest)
    previous = binder.assembly_hash
    if binder.state == BinderState.ASSEMBLED and previous == digest:
        raise Conflict("nothing has changed since the last assembly; the file hash is the same")
    binder.state = BinderState.ASSEMBLED
    binder.assembled_at = now
    binder.assembly_hash = digest
    session.flush()
    details: dict[str, Any] = {
        "file_hash": digest,
        "previous_file_hash": previous,
        "manifest": manifest,
    }
    _, version = spine_blocker(spine, binder)
    if version is not None:
        details["spine_version"] = {
            "version_id": str(version.version_id),
            "label": version.label,
            "hash": version.hash,
            "locked_at": version.locked_at.isoformat() if version.locked_at else None,
        }
        # The lines every FS-line reference was just verified against travel with the
        # event, so the produced file never needs the Spine again (D30).
        lines = fs_line_service.for_binder(spine, binder)
        if lines.available:
            details["fs_lines"] = fs_line_service.to_record(lines, version.version_id)
    return record(session, binder, EventKind.ASSEMBLED, user, now, details=details)


def assembled_lines(session: Session, binder: Binder) -> fs_line_service.FsLines | None:
    """The FS lines recorded by the most recent assembly (D30), or None when that assembly
    recorded none: a binder assembled before lines were recorded, or one assembled without
    a readable Spine version."""
    for event in reversed(events(session, binder)):
        if event.kind == EventKind.ASSEMBLED:
            return fs_line_service.from_record(event.details.get("fs_lines"))
    return None


# --- post-assembly amendments (spec 3F, 8.4) --------------------------------------------------


def require_reason(reason: str | None) -> str:
    """The amendment reason every post-assembly change needs (spec 3F), trimmed."""
    text = (reason or "").strip()
    if not text:
        raise Invalid("a post-assembly change needs an amendment reason (spec 3F)")
    return text


_require_reason = require_reason


def _amendment_version(
    session: Session, paper: Wp, reason: str, user: str, now: datetime
) -> WpVersion:
    body = paper_service.snapshot(session, paper)
    version = WpVersion(
        wp_id=paper.id,
        version=paper_service.next_version_number(session, paper),
        body=body,
        prepared_by=user,
        prepared_at=now,
        content_hash=content_hash(body),
        amendment_reason=reason,
    )
    # The amended content is unsigned: back to draft, with the amendment as current version.
    paper_service.append_version(session, paper, version, WpStatus.DRAFT)
    return version


def amend(
    session: Session,
    paper: Wp,
    changes: Mapping[str, Any],
    *,
    reason: str | None,
    user: str,
    now: datetime,
) -> WpVersion:
    """Change a paper in an assembled binder: a new version carrying reason, author and
    date, and an event so the manifest history records the amendment. Nothing is
    overwritten (spec 3F, 8.4)."""
    binder = paper_service.binder_of(session, paper)
    if binder.state != BinderState.ASSEMBLED:
        raise Conflict("amendments apply to an assembled binder; edit an open binder directly")
    text = _require_reason(reason)
    if "ref" in changes:
        raise Invalid("the reference is stable and cannot be changed (spec 3B)")
    paper_service.refuse_locked(session, paper, changes)
    cleaned = paper_service.validate_content(changes)
    if not paper_service.apply_changes(paper, cleaned):
        raise Invalid("the amendment changes nothing")
    session.flush()
    version = _amendment_version(session, paper, text, user, now)
    record(
        session,
        binder,
        EventKind.AMENDED,
        user,
        now,
        reason=text,
        details={
            "ref": paper.ref,
            "wp_id": str(paper.id),
            "version": version.version,
            "fields": sorted(cleaned),
        },
    )
    return version


def amend_attach(
    session: Session,
    store: AttachmentStore,
    paper: Wp,
    *,
    filename: str,
    data: bytes,
    identifying_chars: str | None,
    reason: str | None,
    user: str,
    now: datetime,
    max_bytes: int,
) -> tuple[WpAttachment, WpVersion]:
    """Attach evidence to a paper in an assembled binder, as an amendment."""
    binder = paper_service.binder_of(session, paper)
    if binder.state != BinderState.ASSEMBLED:
        raise Conflict("amendments apply to an assembled binder; attach to an open binder directly")
    text = _require_reason(reason)
    row = _attach_row(
        session,
        store,
        paper,
        filename=filename,
        data=data,
        identifying_chars=identifying_chars,
        user=user,
        now=now,
        max_bytes=max_bytes,
    )
    version = _amendment_version(session, paper, text, user, now)
    row.wp_version_id = version.id
    session.flush()
    record(
        session,
        binder,
        EventKind.AMENDED,
        user,
        now,
        reason=text,
        details={
            "ref": paper.ref,
            "wp_id": str(paper.id),
            "version": version.version,
            "attachment": row.sha256,
            "filename": row.filename,
        },
    )
    return row, version


# --- verification (spec 8.5) ------------------------------------------------------------------


@dataclass
class Check:
    item: str
    ok: bool
    detail: str


@dataclass
class Verification:
    ok: bool
    assembly_hash: str | None
    recomputed_from_recorded_manifest: str | None
    current_file_hash: str
    current_matches_assembled: bool
    checks: list[Check] = field(default_factory=list)


def verify(session: Session, store: AttachmentStore, binder: Binder) -> Verification:
    """Recompute everything that was hashed and compare it with what was recorded:
    every version body against its content hash, every stored file against its SHA-256, and
    the recorded manifest against the recorded file hash. Also says whether the file as it
    stands now still matches the assembled manifest (false after an amendment until the
    binder is re-assembled)."""
    checks: list[Check] = []
    papers = session.scalars(select(Wp).where(Wp.binder_id == binder.id).order_by(Wp.ref)).all()
    for paper in papers:
        for version in paper_service.versions(session, paper):
            digest = content_hash(version.body)
            checks.append(
                Check(
                    f"paper {paper.ref} version {version.version}",
                    digest == version.content_hash,
                    "content hash reproduces"
                    if digest == version.content_hash
                    else f"recorded {version.content_hash[:12]}…, recomputed {digest[:12]}…",
                )
            )
        for attachment in session.scalars(
            select(WpAttachment).where(WpAttachment.wp_id == paper.id)
        ).all():
            try:
                verified_read(store, attachment)
            except Exception as exc:  # noqa: BLE001  # every failure is a finding here
                checks.append(Check(f"attachment {attachment.filename}", False, str(exc)))
            else:
                checks.append(
                    Check(f"attachment {attachment.filename}", True, "stored bytes match hash")
                )
    recorded = latest_manifest(session, binder)
    recomputed = file_hash(recorded) if recorded is not None else None
    if binder.assembly_hash is not None:
        checks.append(
            Check(
                "assembly manifest",
                recomputed == binder.assembly_hash,
                "recorded manifest reproduces the file hash"
                if recomputed == binder.assembly_hash
                else "the recorded manifest does not reproduce the recorded file hash",
            )
        )
    current = file_hash(build_manifest(session, binder))
    return Verification(
        ok=all(c.ok for c in checks),
        assembly_hash=binder.assembly_hash,
        recomputed_from_recorded_manifest=recomputed,
        current_file_hash=current,
        current_matches_assembled=current == binder.assembly_hash,
        checks=checks,
    )
