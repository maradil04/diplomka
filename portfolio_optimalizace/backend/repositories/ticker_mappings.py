from flask import has_app_context

from backend.db import get_connection, get_db


def _fetch_all(query, params):
    if has_app_context():
        return get_db().execute(query, params).fetchall()

    conn = get_connection()
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def _execute(query, params):
    if has_app_context():
        db = get_db()
        cursor = db.execute(query, params)
        db.commit()
        return cursor.rowcount

    conn = get_connection()
    try:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_ticker_mapping(input_ticker):
    if not input_ticker:
        return None
    rows = _fetch_all(
        """
        SELECT input_ticker, provider_ticker, exchange, currency, resolution_source, confirmed, created_at, updated_at
        FROM ticker_symbol_mappings
        WHERE input_ticker = %s
        """,
        (input_ticker,),
    )
    return dict(rows[0]) if rows else None


def upsert_ticker_mapping(*, input_ticker, provider_ticker, exchange=None, currency=None, resolution_source="manual", confirmed=True):
    if not input_ticker or not provider_ticker:
        return 0
    return _execute(
        """
        INSERT INTO ticker_symbol_mappings (
            input_ticker, provider_ticker, exchange, currency, resolution_source, confirmed
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (input_ticker) DO UPDATE SET
            provider_ticker = EXCLUDED.provider_ticker,
            exchange = EXCLUDED.exchange,
            currency = EXCLUDED.currency,
            resolution_source = EXCLUDED.resolution_source,
            confirmed = EXCLUDED.confirmed,
            updated_at = CURRENT_TIMESTAMP
        """,
        (input_ticker, provider_ticker, exchange, currency, resolution_source, confirmed),
    )
