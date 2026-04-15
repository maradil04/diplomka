from backend.db import get_db


def replace_portfolio_transactions(*, portfolio_id, transaction_records, filename=None):
    db = get_db()
    db.execute("DELETE FROM portfolio_transactions WHERE portfolio_id = %s", (portfolio_id,))
    db.execute("DELETE FROM portfolio_imports WHERE portfolio_id = %s", (portfolio_id,))

    if transaction_records:
        with db.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO portfolio_transactions (
                    portfolio_id, date, ticker, type, quantity, total_amount, total_amount_original_curr, currency, raw_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        portfolio_id,
                        record.get("date"),
                        record.get("ticker"),
                        record.get("type"),
                        record.get("quantity"),
                        record.get("total_amount"),
                        record.get("total_amount_original_curr"),
                        record.get("currency"),
                        record.get("raw_json"),
                    )
                    for record in transaction_records
                ],
            )

    db.execute(
        """
        INSERT INTO portfolio_imports (portfolio_id, filename, row_count, status)
        VALUES (%s, %s, %s, %s)
        """,
        (portfolio_id, filename, len(transaction_records), "completed"),
    )
    db.commit()


def list_portfolio_transactions(portfolio_id):
    rows = get_db().execute(
        """
        SELECT id, portfolio_id, date, ticker, type, quantity, total_amount, total_amount_original_curr, currency, raw_json, created_at
        FROM portfolio_transactions
        WHERE portfolio_id = %s
        ORDER BY id ASC
        """,
        (portfolio_id,),
    ).fetchall()
    return [dict(row) for row in rows]
