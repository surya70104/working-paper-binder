"""The access log (spec 3H, 4; D25): who opened the file after assembly.

"Opened" is read as any read of an assembled or purged binder's content: the binder, a
paper, its versions, its review notes, its cross-references, an attachment's details or
bytes, the binder's review notes, the assembly status, a verification, a production. Reads of
an open binder are ordinary work and are not logged. Because the log must say who, a read
of an assembled file requires an identity where a read of an open file does not.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from oak_binder.identity import current_user, optional_user
from oak_binder.models import AccessLog, Binder, BinderState

LOGGED_STATES = (BinderState.ASSEMBLED, BinderState.PURGED)


def is_logged(binder: Binder) -> bool:
    return binder.state in LOGGED_STATES


def reader(request: Request, binder: Binder) -> str | None:
    """The identity to log for a read. For an assembled or purged file it is required, so
    the identity dependency's refusal applies; for an open file it is optional."""
    if is_logged(binder):
        return current_user(request)
    return optional_user(request)


def record(
    session: Session, binder: Binder, user: str | None, action: str, now: datetime
) -> AccessLog | None:
    """Write one row if the binder is past assembly; otherwise nothing."""
    if not is_logged(binder):
        return None
    assert user, "a read of an assembled file always has an identity"  # noqa: S101
    row = AccessLog(binder_id=binder.id, user=user, action=action, at=now)
    session.add(row)
    session.flush()
    return row


def for_binder(session: Session, binder: Binder) -> list[AccessLog]:
    return list(
        session.scalars(
            select(AccessLog)
            .where(AccessLog.binder_id == binder.id)
            .order_by(AccessLog.at, AccessLog.id)
        ).all()
    )
