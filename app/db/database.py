"""SQLAlchemy engine, sessions, and SQLite initialization helpers."""
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


_engine: Engine | None = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)


def create_database_engine(database_url: str, echo: bool = False) -> Engine:
    """Create an SQLAlchemy engine and attach SQLite resilience pragmas."""
    url = make_url(database_url)
    connect_args: dict[str, Any] = {}
    if url.drivername.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        _ensure_sqlite_parent_dir(url.database)

    engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args)

    if url.drivername.startswith("sqlite"):
        _attach_sqlite_pragmas(engine)

    return engine


def get_engine(settings: Settings | None = None) -> Engine:
    """Return the process-wide database engine."""
    global _engine
    if _engine is None:
        active_settings = settings or get_settings()
        _engine = create_database_engine(
            active_settings.database_url,
            echo=active_settings.database_echo,
        )
        SessionLocal.configure(bind=_engine)
    return _engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database(settings: Settings | None = None) -> None:
    """Create missing tables and seed required baseline records."""
    from app.db import models  # noqa: F401
    from app.services.course_service import seed_default_courses
    from app.services.queue_service import seed_active_session

    engine = get_engine(settings)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_default_courses(db)
        seed_active_session(db)
        db.commit()


def database_health(settings: Settings | None = None) -> dict[str, str | bool]:
    """Return a small health snapshot for status endpoints."""
    active_settings = settings or get_settings()
    try:
        engine = get_engine(active_settings)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "status": "initialized",
            "type": "sqlite" if active_settings.database_url.startswith("sqlite") else "unknown",
            "path": active_settings.database_url,
            "connected": True,
        }
    except Exception as exc:  # pragma: no cover - defensive status path
        return {
            "status": "error",
            "type": "sqlite" if active_settings.database_url.startswith("sqlite") else "unknown",
            "path": active_settings.database_url,
            "connected": False,
            "error": str(exc),
        }


def reset_engine_for_tests() -> None:
    """Dispose the cached engine so tests can switch database URLs."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal.configure(bind=None)


def _ensure_sqlite_parent_dir(database_path: str | None) -> None:
    if not database_path or database_path == ":memory:":
        return
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


def _attach_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

