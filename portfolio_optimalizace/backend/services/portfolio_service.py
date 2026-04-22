import json

import pandas as pd
from flask import session

from backend.repositories.portfolios import (
    create_portfolio,
    delete_portfolio_for_user,
    ensure_default_portfolio,
    get_most_recent_portfolio_for_user,
    get_portfolio_for_user,
    list_portfolios_for_user,
)
from backend.repositories.transactions import list_portfolio_transactions


TRANSACTION_COLUMNS = [
    "Date",
    "Ticker",
    "Type",
    "Quantity",
    "Price per share",
    "Total Amount",
    "Total Amount Original Curr",
    "Currency",
    "FX Rate",
]


def empty_transactions_dataframe():
    return pd.DataFrame(columns=TRANSACTION_COLUMNS)


def parse_money_series(series):
    if series is None:
        return pd.Series(dtype=float)
    values = series.fillna("").astype(str).str.strip()
    values = values.str.replace("\u00A0", "", regex=False).str.replace(" ", "", regex=False)
    values = values.str.replace("€", "", regex=False)
    values = values.str.replace("â‚¬", "", regex=False).str.replace("Ă˘â€šÂ¬", "", regex=False)
    values = values.apply(_normalize_money_value)
    return pd.to_numeric(values, errors="coerce")


def _normalize_money_value(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""

    if "," in value and "." not in value:
        head, tail = value.rsplit(",", 1)
        if tail.isdigit() and len(tail) == 3:
            value = head.replace(",", "") + tail
        else:
            value = head.replace(",", "") + "." + tail
    elif "." in value and "," not in value:
        head, tail = value.rsplit(".", 1)
        if tail.isdigit() and len(tail) == 3 and head.replace(".", "").replace("-", "").isdigit():
            value = head.replace(".", "") + tail
    elif "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")

    value = "".join(ch for ch in value if ch.isdigit() or ch in ".-")
    return value


def calculate_net_invested_capital(dataframe: pd.DataFrame, target_date=None) -> float:
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        return 0.0

    working = dataframe.copy()
    if "Type" not in working.columns or "Total Amount" not in working.columns:
        return 0.0

    if "Date" in working.columns:
        working["Date"] = pd.to_datetime(working["Date"], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
        if target_date is not None:
            target_date = pd.to_datetime(target_date, errors="coerce", utc=True)
            if pd.notna(target_date):
                target_date = target_date.tz_convert(None).normalize()
                working = working[working["Date"] <= target_date]

    type_series = working["Type"].fillna("").astype(str)
    amounts = parse_money_series(working["Total Amount"]).fillna(0.0).abs()
    topups = amounts[type_series.eq("CASH TOP-UP")].sum()
    withdrawals = amounts[type_series.eq("CASH WITHDRAWAL")].sum()
    return float(round(topups - withdrawals, 2))


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
        if not portfolios:
            return None

    remembered = session.get("active_portfolio_id")
    if remembered:
        try:
            remembered_int = int(remembered)
        except (TypeError, ValueError):
            remembered_int = None

        if remembered_int:
            portfolio = get_portfolio_for_user(user_id, remembered_int)
            if portfolio:
                return portfolio

    return portfolios[0] if portfolios else None


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


def delete_user_portfolio(user_id, portfolio_id):
    portfolio = get_portfolio_for_user(user_id, portfolio_id)
    if not portfolio:
        return None, list_portfolios_for_user(user_id)

    delete_portfolio_for_user(user_id, portfolio_id)
    remaining = list_portfolios_for_user(user_id)
    if not remaining:
        replacement = ensure_default_portfolio(user_id)
        remaining = [replacement] if replacement else []
    active = resolve_active_portfolio(user_id)
    return active, remaining


def load_portfolio_transactions_dataframe(user_id, portfolio_id, fallback=None):
    if not user_id or not portfolio_id:
        if isinstance(fallback, pd.DataFrame):
            return fallback.copy()
        return empty_transactions_dataframe() if fallback is None else fallback

    portfolio = get_portfolio_for_user(user_id, portfolio_id)
    if not portfolio:
        if isinstance(fallback, pd.DataFrame):
            return fallback.copy()
        return empty_transactions_dataframe() if fallback is None else fallback

    rows = list_portfolio_transactions(portfolio_id)
    if not rows:
        if isinstance(fallback, pd.DataFrame):
            return fallback.copy()
        return empty_transactions_dataframe() if fallback is None else fallback

    parsed_rows = []
    for row in rows:
        raw_json = row.get("raw_json")
        if raw_json:
            try:
                payload = json.loads(raw_json)
                payload["Total Amount"] = row.get("total_amount")
                payload["Total Amount Original Curr"] = row.get("total_amount_original_curr", row.get("total_amount"))
                payload["Currency"] = row.get("currency", payload.get("Currency"))
                parsed_rows.append(payload)
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
                "Total Amount Original Curr": row.get("total_amount_original_curr", row.get("total_amount")),
                "Currency": row.get("currency"),
            }
        )

    dataframe = pd.DataFrame(parsed_rows)
    if dataframe.empty:
        if isinstance(fallback, pd.DataFrame):
            return fallback.copy()
        return empty_transactions_dataframe() if fallback is None else fallback

    for column in TRANSACTION_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = None
    return dataframe[TRANSACTION_COLUMNS]
