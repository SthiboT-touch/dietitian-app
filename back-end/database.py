"""Open database connections for API routes and AI tools.

Keep connection details in the environment, not in application logs. All
routes should use ``cursor()`` so connections close after each operation.
"""

import logging
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

sqlite3.register_converter("DATE", lambda value: date.fromisoformat(value.decode()))
sqlite3.register_converter("JSON", lambda value: json.loads(value.decode()))
sqlite3.register_converter(
    "TIMESTAMP",
    lambda value: datetime.fromisoformat(value.decode().replace("Z", "+00:00")),
)
sqlite3.register_converter(
    "TIMESTAMPTZ",
    lambda value: datetime.fromisoformat(value.decode().replace("Z", "+00:00")),
)


def connection_options():
    """Build connection options without exposing credentials in error output.

    A separate ``DB_PASSWORD`` takes precedence over the URL password. This
    avoids problems when passwords contain characters special to URLs.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    parts = urlsplit(database_url)
    if parts.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("DATABASE_URL must start with postgresql://")

    password = os.environ.get("DB_PASSWORD")
    if password is None:
        password = unquote(parts.password or "")

    return {
        "host": os.environ.get("DB_HOST") or parts.hostname or "db",
        "port": int(os.environ.get("DB_PORT") or parts.port or 5432),
        "user": os.environ.get("DB_USER") or unquote(parts.username or ""),
        "password": password,
        "dbname": os.environ.get("DB_NAME") or unquote(parts.path.lstrip("/")),
        "connect_timeout": 8,
    }


def is_sqlite():
    return urlsplit(os.environ.get("DATABASE_URL", "")).scheme == "sqlite"


def _sqlite_path(database_url):
    configured_path = os.environ.get("SQLITE_PATH")
    if configured_path:
        path = Path(configured_path)
    else:
        parts = urlsplit(database_url)
        if parts.scheme != "sqlite" or parts.netloc:
            raise RuntimeError("SQLite DATABASE_URL must use sqlite:///path/to/file.db")
        raw_path = unquote(parts.path)
        if raw_path in ("", "/", "/:memory:"):
            raise RuntimeError("SQLite requires a persistent file path; use in-memory mode for temporary data")
        if raw_path.startswith("//"):
            raw_path = raw_path[1:]
        elif raw_path.startswith("/"):
            raw_path = raw_path[1:]
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class _SQLiteCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, parameters=()):
        if "pg_advisory_xact_lock" in query.lower():
            if not self._cursor.connection.in_transaction:
                self._cursor.connection.execute("BEGIN IMMEDIATE")
            query, parameters = "SELECT 1", ()
        elif re.search(r"\bFOR UPDATE\b", query, flags=re.IGNORECASE):
            if not self._cursor.connection.in_transaction:
                self._cursor.connection.execute("BEGIN IMMEDIATE")
        query = re.sub(r"::jsonb\b", "", query, flags=re.IGNORECASE)
        query = re.sub(r"\bNOW\(\)", "CURRENT_TIMESTAMP", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+FOR UPDATE(?:\s+SKIP LOCKED)?\b", "", query, flags=re.IGNORECASE)
        query = re.sub(r"%s", "?", query)
        self._cursor.execute(query, parameters)
        return self

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def initialize_sqlite_schema(connection):
    """Create the current SQLite schema and lookup rows for a new database."""
    schema_path = Path(__file__).with_name("dietitainDB.sql")
    schema = schema_path.read_text(encoding="utf-8")
    schema = schema.replace("CREATE EXTENSION IF NOT EXISTS pgcrypto;", "")
    schema = schema.replace(
        "DEFAULT gen_random_uuid()::VARCHAR", "DEFAULT (gen_random_uuid())"
    )
    schema = schema.replace("::VARCHAR", "")
    schema = schema.replace("BYTEA", "BLOB")
    schema = schema.replace("DEFAULT (NOW() + INTERVAL '10 minutes')", "DEFAULT (datetime('now', '+10 minutes'))")
    schema = schema.replace("DEFAULT NOW()", "DEFAULT CURRENT_TIMESTAMP")
    schema = schema.replace(
        "registered_by_staff_id VARCHAR(36),",
        "registered_by_staff_id VARCHAR(36) REFERENCES staff_account(staff_id) ON DELETE SET NULL,",
    )
    schema = schema.replace(
        "ALTER TABLE client_registration_consent ADD CONSTRAINT fk_registration_staff "
        "FOREIGN KEY (registered_by_staff_id) REFERENCES staff_account(staff_id) ON DELETE SET NULL;",
        "",
    )
    schema += """
    CREATE TABLE IF NOT EXISTS meal_plan_review (
        plan_id TEXT PRIMARY KEY,
        client_id TEXT NOT NULL,
        dietitian_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING_REVIEW'
            CHECK (status IN ('PENDING_REVIEW', 'APPROVED', 'MODIFIED', 'REJECTED')),
        draft_json JSON NOT NULL,
        approved_json JSON,
        review_note TEXT,
        reviewed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (
            (status = 'PENDING_REVIEW' AND reviewed_at IS NULL AND approved_json IS NULL) OR
            (status = 'REJECTED' AND reviewed_at IS NOT NULL AND approved_json IS NULL) OR
            (status IN ('APPROVED', 'MODIFIED') AND reviewed_at IS NOT NULL AND approved_json IS NOT NULL)
        )
    );
    CREATE INDEX IF NOT EXISTS idx_meal_plan_review_client
        ON meal_plan_review(client_id, status);
    CREATE INDEX IF NOT EXISTS idx_meal_plan_review_dietitian
        ON meal_plan_review(dietitian_id, status);
    """
    connection.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))
    connection.executescript(schema)


def open_connection():
    """Connect using the configured PostgreSQL or SQLite URL."""
    database_url = os.environ.get("DATABASE_URL", "")
    if urlsplit(database_url).scheme == "sqlite":
        connection = sqlite3.connect(
            _sqlite_path(database_url), timeout=8, detect_types=sqlite3.PARSE_DECLTYPES
        )
        connection.row_factory = sqlite3.Row
        connection.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))
        connection.execute("PRAGMA foreign_keys = ON")
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='business'"
        ).fetchone():
            initialize_sqlite_schema(connection)
        return connection

    try:
        return psycopg2.connect(**connection_options())
    except psycopg2.OperationalError:
        logger.warning(
            "Could not connect to PostgreSQL. Check that the database is "
            "running and that the API credentials match its stored credentials."
        )
        raise


@contextmanager
def cursor():
    """Provide a mapping-style cursor and always release its connection.

    Both backends commit on success and roll back if the caller raises.
    """
    connection = open_connection()
    try:
        with connection:
            if isinstance(connection, sqlite3.Connection):
                yield _SQLiteCursor(connection.cursor())
            else:
                with connection.cursor(cursor_factory=RealDictCursor) as db_cursor:
                    yield db_cursor
    finally:
        connection.close()
