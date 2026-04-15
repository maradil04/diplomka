import os
from urllib.parse import urlparse

import psycopg
from flask import g
from dotenv import load_dotenv
from psycopg.rows import dict_row
from pathlib import Path

from backend.models import POST_SCHEMA_MIGRATIONS, SCHEMA_STATEMENTS, TICKER_MAPPING_SEED_ROWS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return database_url


def get_connection():
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def get_db():
    if "db" not in g:
        g.db = get_connection()
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)
            for statement in POST_SCHEMA_MIGRATIONS:
                cursor.execute(statement)
            cursor.executemany(
                """
                INSERT INTO ticker_symbol_mappings (
                    input_ticker, provider_ticker, exchange, currency, resolution_source, confirmed
                )
                VALUES (%s, %s, %s, %s, 'seed', TRUE)
                ON CONFLICT (input_ticker) DO UPDATE SET
                    provider_ticker = EXCLUDED.provider_ticker,
                    exchange = EXCLUDED.exchange,
                    currency = EXCLUDED.currency,
                    resolution_source = EXCLUDED.resolution_source,
                    confirmed = EXCLUDED.confirmed,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ticker_symbol_mappings.resolution_source = 'seed'
                """,
                TICKER_MAPPING_SEED_ROWS,
            )
        conn.commit()
    finally:
        conn.close()


def database_name_from_url() -> str:
    parsed = urlparse(get_database_url())
    return (parsed.path or "").lstrip("/")
