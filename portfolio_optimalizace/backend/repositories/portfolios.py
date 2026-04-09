from backend.db import get_db


def list_portfolios_for_user(user_id):
    rows = get_db().execute(
        """
        SELECT id, user_id, name, base_currency, source_filename, source_portfolio_id,
               derived_from, effective_start_date, baseline_invested_capital, created_at, updated_at
        FROM portfolios
        WHERE user_id = %s
        ORDER BY updated_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_portfolio_for_user(user_id, portfolio_id):
    if not user_id or not portfolio_id:
        return None
    row = get_db().execute(
        """
        SELECT id, user_id, name, base_currency, source_filename, source_portfolio_id,
               derived_from, effective_start_date, baseline_invested_capital, created_at, updated_at
        FROM portfolios
        WHERE id = %s AND user_id = %s
        """,
        (portfolio_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def get_most_recent_portfolio_for_user(user_id):
    rows = list_portfolios_for_user(user_id)
    return rows[0] if rows else None


def create_portfolio(
    *,
    user_id,
    name,
    base_currency="EUR",
    source_filename=None,
    source_portfolio_id=None,
    derived_from=None,
    effective_start_date=None,
    baseline_invested_capital=None,
):
    db = get_db()
    row = db.execute(
        """
        INSERT INTO portfolios (
            user_id, name, base_currency, source_filename,
            source_portfolio_id, derived_from, effective_start_date, baseline_invested_capital
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            user_id,
            name,
            base_currency,
            source_filename,
            source_portfolio_id,
            derived_from,
            effective_start_date,
            baseline_invested_capital,
        ),
    ).fetchone()
    db.commit()
    return get_portfolio_for_user(user_id, row["id"])


def ensure_default_portfolio(user_id):
    existing = get_most_recent_portfolio_for_user(user_id)
    if existing:
        return existing
    return create_portfolio(user_id=user_id, name="My Portfolio")


def update_portfolio_metadata(
    *,
    portfolio_id,
    source_filename=None,
    source_portfolio_id=None,
    derived_from=None,
    effective_start_date=None,
    baseline_invested_capital=None,
):
    db = get_db()
    db.execute(
        """
        UPDATE portfolios
        SET source_filename = COALESCE(%s, source_filename),
            source_portfolio_id = COALESCE(%s, source_portfolio_id),
            derived_from = COALESCE(%s, derived_from),
            effective_start_date = COALESCE(%s, effective_start_date),
            baseline_invested_capital = COALESCE(%s, baseline_invested_capital),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            source_filename,
            source_portfolio_id,
            derived_from,
            effective_start_date,
            baseline_invested_capital,
            portfolio_id,
        ),
    )
    db.commit()


def delete_portfolio_for_user(user_id, portfolio_id):
    if not user_id or not portfolio_id:
        return False
    db = get_db()
    cursor = db.execute(
        """
        DELETE FROM portfolios
        WHERE id = %s AND user_id = %s
        """,
        (portfolio_id, user_id),
    )
    db.commit()
    return cursor.rowcount > 0
