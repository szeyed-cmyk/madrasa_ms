"""SQLAlchemy engine/session plus a numbered SQLite migrator (table schema_migrations).

All application queries use the SQLAlchemy ORM / Core with bound parameters. The only SQL text in the
project is in this file: PRAGMAs and the ALTER TABLE of migration 1, whose table/column names come from
app/models.py and are validated + quoted by _quote(); no user input ever reaches SQL text.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, event, insert, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(db_path):
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(eng, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return eng


engine = make_engine(settings.database_path)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sql_default(column) -> str:
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return ""
    value = default.arg
    if isinstance(value, bool):
        return f" DEFAULT {1 if value else 0}"
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        return " DEFAULT '" + value.replace("'", "''") + "'"
    return ""


# Tables of removed features. 1.2.0 removed the mock SMS system, so its log table is dropped on upgrade.
OBSOLETE_TABLES = ("sms_logs",)
IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# Numbered, recorded migrations (table schema_migrations). Version 1 is the additive sync below and
# runs on every start (new columns of new versions). Versions >= 2 run once, in order, and are recorded.
# Before a one-time migration touches an existing database, a copy is saved in data/backups/ so the
# upgrade can be rolled back by restoring that file.
MIGRATIONS: list[tuple[int, str]] = [
    (1, "baseline: create missing tables, add missing columns, drop tables of removed features"),
    (2, "1.0.2: index every foreign key and the frequent filters (attendance, payments, marks)"),
    (3, "1.0.4: login_attempts table for the persistent login throttle"),
    (4, "1.0.5: app_settings, currencies, languages, translations tables + branding columns"),
]
SCHEMA_VERSION = MIGRATIONS[-1][0]


def _quote(eng, name: str) -> str:
    """Quote a table/column name that comes from app/models.py (never from user input)."""
    if not IDENTIFIER_RE.match(name):
        raise ValueError(f"Unexpected identifier {name!r}")
    return eng.dialect.identifier_preparer.quote(name)


def _sync_columns(eng, conn, insp) -> list[str]:
    """Migration 1 (every start): drop removed-feature tables and add columns that models have."""
    added: list[str] = []
    for name in OBSOLETE_TABLES:
        if insp.has_table(name):
            Table(name, MetaData()).drop(conn)
    for table in Base.metadata.sorted_tables:
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            coltype = column.type.compile(dialect=eng.dialect)
            # DDL cannot take bound parameters for names; both names are validated model identifiers.
            ddl = f"ALTER TABLE {_quote(eng, table.name)} ADD COLUMN {_quote(eng, column.name)} {coltype}"
            conn.execute(text(ddl + _sql_default(column)))
            added.append(f"{table.name}.{column.name}")
    return added


def _create_indexes(conn) -> None:
    """Migration 2: indexes declared in models.py (CREATE INDEX IF NOT EXISTS)."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(conn, checkfirst=True)


def _backup(eng, version: int) -> Path | None:
    """Copy the SQLite file to data/backups/ before a one-time migration (rollback = restore the copy)."""
    path = eng.url.database
    if not path or path == ":memory:" or not Path(path).is_file():
        return None
    target_dir = Path(path).parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{Path(path).stem}-before-migration-{version}-{datetime.now():%Y%m%d-%H%M%S}.db"
    src, dst = sqlite3.connect(path), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return target


def applied_versions(eng=None) -> list[int]:
    from .models import SchemaMigration  # local import: models import Base from this module

    eng = eng or engine
    with eng.connect() as conn:
        return [row[0] for row in conn.execute(select(SchemaMigration.version).order_by(SchemaMigration.version))]


def migrate(eng=None) -> list[str]:
    """Bring any older database (1.0 / 1.1.x / 1.2.x / 1.3.0 / 1.0.1) up to the current schema.

    Existing data is never changed. Returns the added columns (e.g. "school_settings.working_days").
    """
    from .models import SchemaMigration  # local import: models import Base from this module

    eng = eng or engine
    insp = inspect(eng)
    had_tables = insp.has_table("students")
    Base.metadata.create_all(bind=eng)
    insp = inspect(eng)
    with eng.begin() as conn:
        added = _sync_columns(eng, conn, insp)
        done = set(conn.execute(select(SchemaMigration.version)).scalars())
    pending = [(v, name) for v, name in MIGRATIONS if v not in done]
    if had_tables and any(v >= 2 for v, _ in pending):
        _backup(eng, pending[-1][0])
    with eng.begin() as conn:
        for version, name in pending:
            if version in (2, 3, 4):  # 3/4: the new tables themselves are created by create_all above
                _create_indexes(conn)
            now = datetime.now(UTC).replace(tzinfo=None)
            conn.execute(insert(SchemaMigration).values(version=version, name=name[:120], applied_at=now))
    return added
