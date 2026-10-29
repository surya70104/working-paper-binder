"""SQLAlchemy base class, engine and session factories. Importing this module connects to
nothing."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for every Binder table."""


def make_engine(url: str) -> Engine:
    """Create an engine for ``url``. The first connection opens on first use, not here."""
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
