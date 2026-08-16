from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


def _make_engine() -> Engine:
    url = get_settings().database_url
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        # SQLite ships with foreign keys off and rollback-journal locking. A
        # test suite that silently skips FK enforcement will happily pass code
        # that Postgres rejects, so turn both on and keep the two backends
        # behaving the same way.
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        return engine

    # pool_pre_ping: a cram school server gets rebooted and the network drops.
    # Without it the first request after an idle night fails on a dead socket.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
