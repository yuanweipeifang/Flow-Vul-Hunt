from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


logger = logging.getLogger("flow_vul_hunt.database")


class Base(DeclarativeBase):
    pass


settings = get_settings()
if settings.database_url.startswith("sqlite:///"):
    db_path = settings.database_url.removeprefix("sqlite:///")
    if db_path != ":memory:":
        Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_schema() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def _alembic_config():
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    return config


def expected_migration_head() -> str:
    try:
        from alembic.script import ScriptDirectory
    except ImportError:
        return "unknown"
    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    return heads[0] if len(heads) == 1 else "unknown"


def run_migrations() -> None:
    try:
        from alembic import command
    except ImportError:
        create_schema()
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        logger.warning("alembic is not installed; schema created from models without migration tracking")
        return

    command.upgrade(_alembic_config(), "head")

