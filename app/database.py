"""Database plumbing: engine, session factory, declarative Base, and get_db().

This module centralises all SQLAlchemy setup so the rest of the app never has to
know how the database is wired up. It exposes:

- `engine`       : the SQLAlchemy engine bound to our SQLite database.
- `SessionLocal` : a factory that produces new Session objects.
- `Base`         : the declarative base every ORM model inherits from.
- `get_db()`     : a FastAPI dependency that yields a request-scoped session and
                   always closes it afterwards.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# `check_same_thread=False` is required for SQLite when used with FastAPI/Uvicorn,
# because a connection may be created on one thread and used on another. This is
# safe for our usage pattern (one Session per request) and is the standard
# SQLite + FastAPI configuration.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
# `autoflush=False` / `autocommit=False` give us explicit control: the service
# layer decides exactly when to commit, which keeps book/cancel operations atomic.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models (SQLAlchemy 2.0 style)."""

    pass


def get_db():
    """FastAPI dependency that provides a database session for one request.

    Yields a Session and guarantees it is closed once the request finishes,
    even if the handler raises. Used via `Depends(get_db)` in the route modules.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
