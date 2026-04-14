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


def _fetch_one(query, params):
    rows = _fetch_all(query, params)
    return rows[0] if rows else None


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


def _execute_many(query, rows):
    if has_app_context():
        db = get_db()
        with db.cursor() as cursor:
            cursor.executemany(query, rows)
        db.commit()
        return

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.executemany(query, rows)
        conn.commit()
    finally:
        conn.close()


def list_market_price_rows(*, tickers=None, start_date=None, end_date=None):
    filters = []
    params = []

    if tickers:
        filters.append("ticker = ANY(%s)")
        params.append(list(tickers))
    if start_date is not None:
        filters.append("date >= %s")
        params.append(start_date)
    if end_date is not None:
        filters.append("date <= %s")
        params.append(end_date)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = _fetch_all(
        f"""
        SELECT ticker, date, open, high, low, close, adjusted_close, volume, exchange, currency, provider
        FROM market_prices
        {where_clause}
        ORDER BY ticker ASC, date ASC
        """,
        tuple(params),
    )
    return [dict(row) for row in rows]


def market_price_coverage(*, tickers):
    if not tickers:
        return {}

    rows = _fetch_all(
        """
        SELECT ticker, MIN(date) AS min_date, MAX(date) AS max_date, COUNT(*) AS row_count
        FROM market_prices
        WHERE ticker = ANY(%s)
        GROUP BY ticker
        """,
        (list(tickers),),
    )
    return {
        row["ticker"]: {
            "min_date": row["min_date"],
            "max_date": row["max_date"],
            "row_count": row["row_count"],
        }
        for row in rows
    }


def upsert_market_price_rows(rows):
    if not rows:
        return 0

    _execute_many(
        """
        INSERT INTO market_prices (
            ticker, date, open, high, low, close, adjusted_close, volume, exchange, currency, provider
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker, date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            adjusted_close = EXCLUDED.adjusted_close,
            volume = EXCLUDED.volume,
            exchange = EXCLUDED.exchange,
            currency = EXCLUDED.currency,
            provider = EXCLUDED.provider,
            updated_at = CURRENT_TIMESTAMP
        """,
        [
            (
                row.get("ticker"),
                row.get("date"),
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("adjusted_close"),
                row.get("volume"),
                row.get("exchange"),
                row.get("currency"),
                row.get("provider") or "eodhd",
            )
            for row in rows
        ],
    )
    return len(rows)


def get_download_lock(ticker):
    row = _fetch_one(
        """
        SELECT ticker, started_at
        FROM market_data_download_locks
        WHERE ticker = %s
        """,
        (ticker,),
    )
    return dict(row) if row else None


def acquire_download_lock(ticker):
    rowcount = _execute(
        """
        INSERT INTO market_data_download_locks (ticker)
        VALUES (%s)
        ON CONFLICT (ticker) DO NOTHING
        """,
        (ticker,),
    )
    return rowcount > 0


def release_download_lock(ticker):
    _execute(
        """
        DELETE FROM market_data_download_locks
        WHERE ticker = %s
        """,
        (ticker,),
    )


def clear_stale_download_locks(*, older_than_seconds):
    if older_than_seconds is None or older_than_seconds <= 0:
        return 0
    rowcount = _execute(
        """
        DELETE FROM market_data_download_locks
        WHERE started_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 second'))
        """,
        (older_than_seconds,),
    )
    return rowcount
