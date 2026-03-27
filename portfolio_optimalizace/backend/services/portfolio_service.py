import json

import pandas as pd
from flask import session

from backend.repositories.portfolios import (
    create_portfolio,
    ensure_default_portfolio,
    get_most_recent_portfolio_for_user,
    get_portfolio_for_user,
    list_portfolios_for_user,
)
from backend.repositories.transactions import list_portfolio_transactions


def list_user_portfolios(user_id):
    if not user_id:
        return []
    return list_portfolios_for_user(user_id)


def resolve_active_portfolio(user_id):
    if not user_id:
        session.pop("active_portfolio_id", None)
        return None

    portfolios = list_portfolios_for_user(user_id)
    if not portfolios:
        default_portfolio = ensure_default_portfolio(user_id)
        portfolios = [default_portfolio] if default_portfolio else []

    remembered = session.get("active_portfolio_id")
    if remembered:
        portfolio = get_portfolio_for_user(user_id, remembered)
        if portfolio:
            return portfolio

    latest = get_most_recent_portfolio_for_user(user_id)
    if latest:
        session["active_portfolio_id"] = latest["id"]
    return latest


def set_active_portfolio(user_id, portfolio_id):
    portfolio = get_portfolio_for_user(user_id, portfolio_id)
    if not portfolio:
        return None
    session["active_portfolio_id"] = portfolio["id"]
    return portfolio


def create_user_portfolio(user_id, name):
    if not user_id:
        return None
    name = (name or "").strip()
    if not name:
        name = "New Portfolio"
    portfolio = create_portfolio(user_id=user_id, name=name)
    session["active_portfolio_id"] = portfolio["id"]
    return portfolio


def load_portfolio_transactions_dataframe(user_id, portfolio_id, fallback=None):
    if not user_id or not portfolio_id:
        return fallback.copy() if isinstance(fallback, pd.DataFrame) else fallback

    portfolio = get_portfolio_for_user(user_id, portfolio_id)
    if not portfolio:
        return fallback.copy() if isinstance(fallback, pd.DataFrame) else fallback

    rows = list_portfolio_transactions(portfolio_id)
    if not rows:
        return fallback.copy() if isinstance(fallback, pd.DataFrame) else fallback

    parsed_rows = []
    for row in rows:
        raw_json = row.get("raw_json")
        if raw_json:
            try:
                parsed_rows.append(json.loads(raw_json))
                continue
            except Exception:
                pass
        parsed_rows.append(
            {
                "Date": row.get("date"),
                "Ticker": row.get("ticker"),
                "Type": row.get("type"),
                "Quantity": row.get("quantity"),
                "Total Amount": row.get("total_amount"),
                "Currency": row.get("currency"),
            }
        )

    dataframe = pd.DataFrame(parsed_rows)
    return dataframe if not dataframe.empty else (fallback.copy() if isinstance(fallback, pd.DataFrame) else fallback)
