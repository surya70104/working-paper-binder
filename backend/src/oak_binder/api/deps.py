"""Request-scoped dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from oak_binder.identity import current_user
from oak_binder.services.spine_client import SpineClient


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


def spine_client(request: Request) -> SpineClient | None:
    """The Financial Spine client OAK_SPINE_URL configures, or None (D29)."""
    client: SpineClient | None = request.app.state.spine_client
    return client


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return datetime.now(UTC).date()


DbSession = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[str, Depends(current_user)]
Now = Annotated[datetime, Depends(now)]
Today = Annotated[date, Depends(today)]
Spine = Annotated[SpineClient | None, Depends(spine_client)]
