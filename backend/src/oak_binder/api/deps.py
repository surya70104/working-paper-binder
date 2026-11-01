"""Request-scoped dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from oak_binder.identity import current_user
from oak_binder.services.spine_client import SpineClient
from oak_binder.services.workmind_client import WorkMindClient


def get_session(request: Request) -> Iterator[Session]:
    """One session per request, committed when the endpoint returns and rolled back when it
    raises. The factory lives on ``app.state`` so tests can swap it for one bound to a
    transaction they roll back.

    Declared with ``scope="function"`` (D41): FastAPI's default runs the code after ``yield``
    once the response has been sent, so a client's next request could read the database before
    this request's commit landed. Observed on the Assembly screen: a GET 36 ms after a
    successful Assemble saw the binder still open while the new event was already there. With
    function scope the commit completes before the response leaves.
    """
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


def workmind_client(request: Request) -> WorkMindClient | None:
    """The WorkMind client OAK_WORKMIND_URL configures, or None (D37)."""
    client: WorkMindClient | None = request.app.state.workmind_client
    return client


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return datetime.now(UTC).date()


DbSession = Annotated[Session, Depends(get_session, scope="function")]
CurrentUser = Annotated[str, Depends(current_user)]
Now = Annotated[datetime, Depends(now)]
Today = Annotated[date, Depends(today)]
Spine = Annotated[SpineClient | None, Depends(spine_client)]
WorkMind = Annotated[WorkMindClient | None, Depends(workmind_client)]
