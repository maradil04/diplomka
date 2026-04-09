import os
import sqlite3
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = PROJECT_ROOT / "app.db"
sys.path.insert(0, str(PROJECT_ROOT))

from backend.models import POST_SCHEMA_MIGRATIONS, SCHEMA_STATEMENTS


def load_environment():
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "backend" / ".env")


def get_database_url():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return database_url


def sqlite_connection():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def postgres_connection():
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def ensure_postgres_schema(conn):
    with conn.cursor() as cursor:
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        for statement in POST_SCHEMA_MIGRATIONS:
            cursor.execute(statement)
    conn.commit()


def load_sqlite_rows(conn, table_name):
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table_name} ORDER BY id ASC").fetchall()]


def migrate_users(sqlite_conn, pg_conn):
    rows = load_sqlite_rows(sqlite_conn, "users")
    with pg_conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                INSERT INTO users (id, google_sub, email, name, avatar_url, created_at, last_login_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    google_sub = EXCLUDED.google_sub,
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    avatar_url = EXCLUDED.avatar_url,
                    created_at = EXCLUDED.created_at,
                    last_login_at = EXCLUDED.last_login_at
                """,
                (
                    row["id"],
                    row["google_sub"],
                    row["email"],
                    row["name"],
                    row["avatar_url"],
                    row["created_at"],
                    row["last_login_at"],
                ),
            )
    pg_conn.commit()


def migrate_portfolios(sqlite_conn, pg_conn):
    rows = load_sqlite_rows(sqlite_conn, "portfolios")
    with pg_conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                INSERT INTO portfolios (
                    id, user_id, name, base_currency, source_filename,
                    source_portfolio_id, derived_from, effective_start_date,
                    baseline_invested_capital, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    name = EXCLUDED.name,
                    base_currency = EXCLUDED.base_currency,
                    source_filename = EXCLUDED.source_filename,
                    source_portfolio_id = EXCLUDED.source_portfolio_id,
                    derived_from = EXCLUDED.derived_from,
                    effective_start_date = EXCLUDED.effective_start_date,
                    baseline_invested_capital = EXCLUDED.baseline_invested_capital,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    row["id"],
                    row["user_id"],
                    row["name"],
                    row["base_currency"],
                    row["source_filename"],
                    row["source_portfolio_id"],
                    row["derived_from"],
                    row["effective_start_date"],
                    row["baseline_invested_capital"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )
    pg_conn.commit()


def migrate_transactions(sqlite_conn, pg_conn):
    rows = load_sqlite_rows(sqlite_conn, "portfolio_transactions")
    with pg_conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                INSERT INTO portfolio_transactions (
                    id, portfolio_id, date, ticker, type, quantity,
                    total_amount, currency, raw_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    portfolio_id = EXCLUDED.portfolio_id,
                    date = EXCLUDED.date,
                    ticker = EXCLUDED.ticker,
                    type = EXCLUDED.type,
                    quantity = EXCLUDED.quantity,
                    total_amount = EXCLUDED.total_amount,
                    currency = EXCLUDED.currency,
                    raw_json = EXCLUDED.raw_json,
                    created_at = EXCLUDED.created_at
                """,
                (
                    row["id"],
                    row["portfolio_id"],
                    row["date"],
                    row["ticker"],
                    row["type"],
                    row["quantity"],
                    row["total_amount"],
                    row["currency"],
                    row["raw_json"],
                    row["created_at"],
                ),
            )
    pg_conn.commit()


def migrate_imports(sqlite_conn, pg_conn):
    rows = load_sqlite_rows(sqlite_conn, "portfolio_imports")
    with pg_conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                INSERT INTO portfolio_imports (
                    id, portfolio_id, filename, uploaded_at, row_count, status
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    portfolio_id = EXCLUDED.portfolio_id,
                    filename = EXCLUDED.filename,
                    uploaded_at = EXCLUDED.uploaded_at,
                    row_count = EXCLUDED.row_count,
                    status = EXCLUDED.status
                """,
                (
                    row["id"],
                    row["portfolio_id"],
                    row["filename"],
                    row["uploaded_at"],
                    row["row_count"],
                    row["status"],
                ),
            )
    pg_conn.commit()


def sync_identity_sequence(pg_conn, table_name):
    with pg_conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence(%s, 'id'),
                COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                true
            )
            """,
            (table_name,),
        )
    pg_conn.commit()


def main():
    load_environment()
    if not SQLITE_PATH.exists():
        raise FileNotFoundError(f"SQLite source DB not found: {SQLITE_PATH}")

    sqlite_conn = sqlite_connection()
    pg_conn = postgres_connection()
    try:
        ensure_postgres_schema(pg_conn)
        migrate_users(sqlite_conn, pg_conn)
        migrate_portfolios(sqlite_conn, pg_conn)
        migrate_transactions(sqlite_conn, pg_conn)
        migrate_imports(sqlite_conn, pg_conn)
        for table_name in ("users", "portfolios", "portfolio_transactions", "portfolio_imports"):
            sync_identity_sequence(pg_conn, table_name)
        print("SQLite -> PostgreSQL migration completed successfully.")
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
