"""Request-scoped dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from oak_binder.identity import current_user


def get_session(request: Request) -> Iterator[Session]:
    """One session per request, committed when the endpoint returns and rolled back when it
    raises. The factory lives on ``app.state`` so tests can swap it for one bound to a
    transaction they roll back."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return datetime.now(UTC).date()


DbSession = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[str, Depends(current_user)]
Now = Annotated[datetime, Depends(now)]
Today = Annotated[date, Depends(today)]
