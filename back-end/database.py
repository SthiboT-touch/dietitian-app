"""Open PostgreSQL connections for API routes and AI tools.

Keep connection details in the environment, not in application logs. All
routes should use ``cursor()`` so connections close after each operation.
"""

import logging
import os
from contextlib import contextmanager
from urllib.parse import unquote, urlsplit

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


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


def open_connection():
    """Connect to PostgreSQL, leaving the original error for local debugging."""
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
    """Provide a dict-style cursor and always release its connection.

    PostgreSQL commits on success and rolls back if the caller raises.
    """
    connection = open_connection()
    try:
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as db_cursor:
                yield db_cursor
    finally:
        connection.close()
