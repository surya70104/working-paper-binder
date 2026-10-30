"""Move existing local attachments into the Google Drive vault (D27).

    python -m oak_binder.vault_migrate          dry run: report what would move, change nothing
    python -m oak_binder.vault_migrate --apply  upload, verify, and rewrite the document ids

What it preserves: every row's SHA-256 (the Binder's own hash, untouched), every version
body and manifest (they list attachments by hash, never by document id), and every
reference: ``wp_attachment.vault_doc_id`` and ``xref.to_vault_doc`` are rewritten together
from the local key to the Drive file id. What it does not do: delete the local files. They
stay as a second copy until the firm decides otherwise.

Each document is uploaded once however many rows share it, verified by hash after upload
and again by reading it back, and committed on its own, so an interrupted run can simply be
run again: a row whose id is already a Drive id is skipped.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from oak_binder.config import Settings, get_settings
from oak_binder.db import make_engine
from oak_binder.errors import BinderError
from oak_binder.hashing import sha256_of_bytes
from oak_binder.models import Wp, WpAttachment, Xref
from oak_binder.services.attachments import AttachmentStore, LocalAttachmentStore
from oak_binder.services.google_drive import TIMEOUT, GoogleDriveStore

LOCAL_KEY = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class Report:
    apply: bool
    documents_found: int = 0
    documents_moved: int = 0
    rows_rewritten: int = 0
    xrefs_rewritten: int = 0
    already_in_vault: int = 0
    problems: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        mode = "APPLIED" if self.apply else "DRY RUN (nothing changed)"
        out = [
            f"{mode}: {self.documents_found} local document(s) found, "
            f"{self.documents_moved} moved, {self.rows_rewritten} attachment row(s) and "
            f"{self.xrefs_rewritten} cross-reference(s) rewritten, "
            f"{self.already_in_vault} row(s) already in the vault",
        ]
        out.extend(f"PROBLEM: {p}" for p in self.problems)
        return out


def migrate(
    session: Session,
    local: AttachmentStore,
    vault: AttachmentStore,
    *,
    apply: bool,
    binder_ids: set[uuid.UUID] | None = None,
) -> Report:
    """Move the local documents of every binder, or of ``binder_ids`` only."""
    report = Report(apply=apply)
    query = select(WpAttachment).order_by(WpAttachment.attached_at)
    if binder_ids is not None:
        query = query.join(Wp, Wp.id == WpAttachment.wp_id).where(Wp.binder_id.in_(binder_ids))
    rows = session.scalars(query).all()
    by_key: dict[str, list[WpAttachment]] = {}
    for row in rows:
        if LOCAL_KEY.match(row.vault_doc_id):
            by_key.setdefault(row.vault_doc_id, []).append(row)
        else:
            report.already_in_vault += 1
    report.documents_found = len(by_key)

    for key, group in by_key.items():
        first = group[0]
        try:
            data = local.read(key)
        except BinderError as exc:
            report.problems.append(f"{key[:12]}… ({first.filename}): {exc}")
            continue
        digest = sha256_of_bytes(data)
        if digest != key or any(r.sha256 != digest for r in group):
            report.problems.append(
                f"{key[:12]}… ({first.filename}): the local bytes do not match the recorded "
                "hash; not moved"
            )
            continue
        if not apply:
            continue
        filename, media_type = first.filename, first.media_type
        try:
            doc_id = vault.put(data, filename=filename, media_type=media_type)
            if sha256_of_bytes(vault.read(doc_id)) != digest:
                report.problems.append(
                    f"{key[:12]}… ({filename}): the vault's copy does not read back with the "
                    "same hash; ids not rewritten"
                )
                continue
        except BinderError as exc:
            # Nothing was written to the database for this document.
            report.problems.append(f"{key[:12]}… ({filename}): {exc}")
            continue
        try:
            rewritten = len(
                session.execute(
                    update(WpAttachment)
                    .where(WpAttachment.vault_doc_id == key)
                    .values(vault_doc_id=doc_id)
                    .returning(WpAttachment.id)
                ).all()
            )
            xrefs = len(
                session.execute(
                    update(Xref)
                    .where(Xref.to_vault_doc == key)
                    .values(to_vault_doc=doc_id)
                    .returning(Xref.id)
                ).all()
            )
            session.commit()
        except Exception:
            session.rollback()  # only this document's rewrite is undone
            raise
        report.documents_moved += 1
        report.rows_rewritten += rewritten
        report.xrefs_rewritten += xrefs
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Move local attachments into the Drive vault")
    parser.add_argument("--apply", action="store_true", help="write; default is a dry run")
    args = parser.parse_args(argv)
    settings: Settings = get_settings()
    database = make_url(settings.database_url).database
    print(f"Database: {database}; local store: {settings.attachments_dir.resolve()}")  # noqa: T201
    engine = make_engine(settings.database_url)
    try:
        with httpx.Client(timeout=TIMEOUT) as http:
            vault = GoogleDriveStore.from_settings(settings, http)
            folder = vault.folder_info()
            print(f"Vault folder: {folder['name']!r}")  # noqa: T201
            with Session(engine) as session:
                report = migrate(
                    session,
                    LocalAttachmentStore(settings.attachments_dir.resolve()),
                    vault,
                    apply=args.apply,
                )
    except BinderError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    finally:
        engine.dispose()
    for line in report.lines():
        print(line)  # noqa: T201
    return 1 if report.problems else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
