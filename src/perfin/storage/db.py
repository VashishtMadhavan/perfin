"""Engine and session factory.

The engine is built from a connection URL, so moving to Postgres later is a
config change (``sqlite:///…`` → ``postgresql+psycopg://…``) with no code edits
here. For SQLite we enable foreign-key enforcement, which is off by default.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from perfin.storage.orm import Base


def _enable_sqlite_fks(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    connect_args = {}
    if url.startswith("sqlite"):
        # Allows the engine to be shared across the CLI's single-threaded flow
        # and any :memory: test sessions.
        connect_args["check_same_thread"] = False
    engine = create_engine(url, echo=echo, connect_args=connect_args)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_fks)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_schema(engine: Engine) -> None:
    """Create all tables. Used for tests and first-run bootstrap; production
    schema changes go through Alembic migrations."""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional session context: commit on success, roll back on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
