from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


IS_SQLITE = settings.database_url.startswith("sqlite")

# SQLite is the dev/self-host default and is used with a threaded worker model
# (pipeline threads, stream sessions, request handlers all write). Without WAL and a
# busy timeout those writers hit "database is locked"; without foreign_keys=ON every
# ondelete=... rule in models.py is silently ignored.
connect_args = {"check_same_thread": False} if IS_SQLITE else {}
if IS_SQLITE:
    # A fresh file-level DB per process is fine here; the timeout absorbs write bursts.
    connect_args["timeout"] = 30

if IS_SQLITE:
    engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
else:
    # Serverless/Postgres: every warm or cold function instance holds at most a couple
    # of pooled connections, and pooled (PgBouncer) endpoints need short recycling.
    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
        pool_recycle=60,
        pool_timeout=15,
    )

if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns introduced after the first release. create_all never alters an existing
# table, so databases created before those fields shipped would fail on the first
# read of the job row. Adding them here keeps the "no migration tool" story honest
# for a self-hosted pilot; Alembic is the upgrade path once schema changes matter.
_ADDITIVE_COLUMNS = {
    "video_jobs": {
        "lease_owner": "VARCHAR(120)",
        "lease_expires_at": "DATETIME",
        "attempt_count": "INTEGER DEFAULT 0",
        "chunk_cursor_frame": "INTEGER DEFAULT 0",
        "segment_keys_json": "TEXT DEFAULT '[]'",
        "confidence_total": "FLOAT DEFAULT 0",
        "confidence_sample_count": "INTEGER DEFAULT 0",
    },
}


def _migrate_additive_columns() -> None:
    existing = inspect(engine)
    with engine.begin() as connection:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if not existing.has_table(table):
                continue
            present = {column["name"] for column in existing.get_columns(table)}
            for name, ddl_type in columns.items():
                if name in present:
                    continue
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


def init_db() -> None:
    # Import models before create_all so SQLAlchemy has all metadata registered.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_additive_columns()
