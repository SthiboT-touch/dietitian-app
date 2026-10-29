"""Copy the current public PostgreSQL tables into a fresh SQLite database."""
import argparse
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import uuid

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_DIR / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import psycopg2


SEED_TABLES = {"life_stage", "medical_condition", "diet_type", "metric_type"}
BATCH_SIZE = 500


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def sqlite_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return value


def copy_table(source_cursor, destination, table_name):
    quoted_table = quote_identifier(table_name)
    source_cursor.execute(f"SELECT * FROM public.{quoted_table}")
    source_columns = [column.name for column in source_cursor.description]
    target_columns = [row[1] for row in destination.execute(f"PRAGMA table_info({quoted_table})")]
    if set(source_columns) != set(target_columns):
        raise RuntimeError(
            f"Schema mismatch for {table_name}: PostgreSQL columns {source_columns}; "
            f"SQLite columns {target_columns}"
        )

    insert_columns = ", ".join(quote_identifier(column) for column in target_columns)
    placeholders = ", ".join("?" for _ in target_columns)
    insert_sql = f"INSERT INTO {quoted_table} ({insert_columns}) VALUES ({placeholders})"
    column_indexes = [source_columns.index(column) for column in target_columns]
    copied = 0
    while rows := source_cursor.fetchmany(BATCH_SIZE):
        values = [
            tuple(sqlite_value(row[index]) for index in column_indexes)
            for row in rows
        ]
        destination.executemany(insert_sql, values)
        copied += len(values)
    return copied


def migrate(sqlite_path):
    source = psycopg2.connect(**database.connection_options())
    source.set_session(isolation_level="REPEATABLE READ", readonly=True)
    destination = None
    try:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3

        destination = sqlite3.connect(sqlite_path)
        destination.execute("PRAGMA foreign_keys = OFF")
        has_schema = destination.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='business'"
        ).fetchone()
        if not has_schema:
            database.initialize_sqlite_schema(destination)

        sqlite_tables = {
            row[0]
            for row in destination.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        with source.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
            )
            postgres_tables = {row[0] for row in cursor.fetchall()}
            missing_tables = postgres_tables - sqlite_tables
            if missing_tables:
                raise RuntimeError(
                    "SQLite schema is missing PostgreSQL tables: "
                    + ", ".join(sorted(missing_tables))
                )

            for table_name in sqlite_tables:
                count = destination.execute(
                    f"SELECT COUNT(*) FROM {quote_identifier(table_name)}"
                ).fetchone()[0]
                if count and table_name not in SEED_TABLES:
                    raise RuntimeError(
                        f"SQLite destination is not empty ({table_name} has {count} rows); "
                        "choose a fresh database file"
                    )

            destination.execute("BEGIN")
            for table_name in SEED_TABLES & sqlite_tables:
                destination.execute(f"DELETE FROM {quote_identifier(table_name)}")

            copied_counts = {}
            for table_name in sorted(postgres_tables):
                copied_counts[table_name] = copy_table(cursor, destination, table_name)

            violations = destination.execute("PRAGMA foreign_key_check").fetchmany(10)
            if violations:
                raise RuntimeError(f"SQLite foreign-key check failed: {violations}")

            for table_name, copied in copied_counts.items():
                actual = destination.execute(
                    f"SELECT COUNT(*) FROM {quote_identifier(table_name)}"
                ).fetchone()[0]
                if actual != copied:
                    raise RuntimeError(
                        f"Row count mismatch for {table_name}: copied {copied}, found {actual}"
                    )
                print(f"{table_name}: {copied} rows")
            destination.commit()
    except Exception:
        if destination is not None:
            destination.rollback()
        raise
    finally:
        if destination is not None:
            destination.close()
        source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        required=True,
        type=Path,
        help="new or empty SQLite database file to receive the PostgreSQL data",
    )
    args = parser.parse_args()
    migrate(args.sqlite_path.resolve())
    print(f"Migration complete: {args.sqlite_path.resolve()}")


if __name__ == "__main__":
    main()