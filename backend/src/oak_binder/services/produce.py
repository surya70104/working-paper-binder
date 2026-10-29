"""Produce file: the complete assembled file as one archive (spec 3G, 8.6; NFRA 7-day
production).

Archive layout:
  manifest.json                     the manifest recorded at the latest assembly
  binder.json                       the binder's fields, state and hashes
  audit_trail.json                  every binder event: assembled, amended, produced, purged
  papers/<ref>/paper.json           the paper's current fields and status
  papers/<ref>/versions/<n>.json    every version: body, preparer, reviewer, signer, hash
  papers/<ref>/attachments/<name>   the original bytes, native format
  CHECKSUMS.sha256                  "<sha256>  <path>" for every other member
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from oak_binder.errors import Conflict
from oak_binder.hashing import sha256_of_bytes
from oak_binder.models import Binder, BinderState, EventKind, Wp, WpAttachment
from oak_binder.services import papers as paper_service
from oak_binder.services.assembly import events, latest_manifest, record
from oak_binder.services.attachments import AttachmentStore

CHECKSUMS = "CHECKSUMS.sha256"


def _json(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str).encode(
        "utf-8"
    )


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "unnamed"


def produce(
    session: Session, store: AttachmentStore, binder: Binder, *, user: str, now: datetime
) -> bytes:
    if binder.state == BinderState.PURGED:
        raise Conflict(
            f"binder for {binder.engagement!r} was purged after retention; "
            "its content no longer exists (only hashed metadata remains)"
        )
    if binder.state != BinderState.ASSEMBLED:
        raise Conflict("produce the file after assembly; an open binder has no manifest yet")
    manifest = latest_manifest(session, binder)
    if manifest is None:
        raise Conflict("no assembly manifest is recorded for this binder")

    members: dict[str, bytes] = {}
    members["manifest.json"] = _json(manifest)
    members["binder.json"] = _json(
        {
            "id": str(binder.id),
            "engagement": binder.engagement,
            "template": binder.template,
            "state": binder.state,
            "report_date": binder.report_date,
            "assembly_due": binder.assembly_due,
            "assembled_at": binder.assembled_at,
            "assembly_hash": binder.assembly_hash,
            "retention_until": binder.retention_until,
            "produced_at": now,
            "produced_by": user,
        }
    )
    members["audit_trail.json"] = _json(
        [
            {
                "kind": e.kind,
                "actor": e.actor,
                "at": e.at,
                "reason": e.reason,
                "details": {k: v for k, v in e.details.items() if k != "manifest"},
            }
            for e in events(session, binder)
        ]
    )
    papers = session.scalars(select(Wp).where(Wp.binder_id == binder.id).order_by(Wp.ref)).all()
    for paper in papers:
        folder = f"papers/{_safe(paper.ref)}"
        members[f"{folder}/paper.json"] = _json(
            {
                "id": str(paper.id),
                "ref": paper.ref,
                "section": paper.section,
                "title": paper.title,
                "sa_refs": list(paper.sa_refs),
                "objective": paper.objective,
                "procedure": paper.procedure,
                "population_sample": paper.population_sample,
                "result": paper.result,
                "conclusion": paper.conclusion,
                "status": paper.status,
                "current_version": paper.current_version,
            }
        )
        for version in paper_service.versions(session, paper):
            members[f"{folder}/versions/{version.version:04d}.json"] = _json(
                {
                    "version": version.version,
                    "body": version.body,
                    "content_hash": version.content_hash,
                    "prepared_by": version.prepared_by,
                    "prepared_at": version.prepared_at,
                    "reviewed_by": version.reviewed_by,
                    "reviewed_at": version.reviewed_at,
                    "signed_off_by": version.signed_off_by,
                    "signed_off_at": version.signed_off_at,
                    "amendment_reason": version.amendment_reason,
                }
            )
        used: set[str] = set()
        for attachment in session.scalars(
            select(WpAttachment).where(WpAttachment.wp_id == paper.id).order_by(WpAttachment.sha256)
        ).all():
            name = _safe(attachment.filename)
            if name in used:
                name = f"{attachment.sha256[:8]}-{name}"
            used.add(name)
            members[f"{folder}/attachments/{name}"] = store.read(attachment.sha256)

    checksums = "".join(
        f"{sha256_of_bytes(data)}  {path}\n" for path, data in sorted(members.items())
    )
    members[CHECKSUMS] = checksums.encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in members.items():
            archive.writestr(path, data)
    data = buffer.getvalue()
    record(
        session,
        binder,
        EventKind.PRODUCED,
        user,
        now,
        details={
            "members": len(members),
            "bytes": len(data),
            "archive_sha256": sha256_of_bytes(data),
            "assembly_hash": binder.assembly_hash,
        },
    )
    return data


def verify_archive(data: bytes) -> list[str]:
    """Problems found in a produced archive; empty means every member matches CHECKSUMS and
    every attachment matches the manifest's hash."""
    problems: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        if CHECKSUMS not in names:
            return [f"{CHECKSUMS} is missing"]
        listed: dict[str, str] = {}
        for line in archive.read(CHECKSUMS).decode("utf-8").splitlines():
            digest, _, path = line.partition("  ")
            listed[path] = digest
        for path in names - {CHECKSUMS}:
            if path not in listed:
                problems.append(f"{path} is not listed in {CHECKSUMS}")
            elif sha256_of_bytes(archive.read(path)) != listed[path]:
                problems.append(f"{path} does not match its checksum")
        for path in set(listed) - names:
            problems.append(f"{path} is listed but missing")
        manifest = json.loads(archive.read("manifest.json"))
        for paper in manifest["papers"]:
            folder = f"papers/{_safe(paper['ref'])}/attachments/"
            present = {sha256_of_bytes(archive.read(p)) for p in names if p.startswith(folder)}
            for attachment in paper["attachments"]:
                if attachment["sha256"] not in present:
                    problems.append(
                        f"attachment {attachment['filename']} of {paper['ref']} is missing "
                        "or altered"
                    )
    return problems
