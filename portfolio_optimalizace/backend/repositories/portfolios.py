from backend.db import get_db


def list_portfolios_for_user(user_id):
    rows = get_db().execute(
        """
        SELECT id, user_id, name, base_currency, source_filename, created_at, updated_at
        FROM portfolios
        WHERE user_id = ?
        ORDER BY datetime(updated_at) DESC, id DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_portfolio_for_user(user_id, portfolio_id):
    if not user_id or not portfolio_id:
        return None
    row = get_db().execute(
        """
        SELECT id, user_id, name, base_currency, source_filename, created_at, updated_at
        FROM portfolios
        WHERE id = ? AND user_id = ?
        """,
        (portfolio_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def get_most_recent_portfolio_for_user(user_id):
    rows = list_portfolios_for_user(user_id)
    return rows[0] if rows else None


def create_portfolio(*, user_id, name, base_currency="EUR", source_filename=None):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO portfolios (user_id, name, base_currency, source_filename)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, name, base_currency, source_filename),
    )
    db.commit()
    return get_portfolio_for_user(user_id, cursor.lastrowid)


def ensure_default_portfolio(user_id):
    existing = get_most_recent_portfolio_for_user(user_id)
    if existing:
        return existing
    return create_portfolio(user_id=user_id, name="My Portfolio")


def update_portfolio_metadata(*, portfolio_id, source_filename=None):
    db = get_db()
    db.execute(
        """
        UPDATE portfolios
        SET source_filename = COALESCE(?, source_filename),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (source_filename, portfolio_id),
    )
    db.commit()
