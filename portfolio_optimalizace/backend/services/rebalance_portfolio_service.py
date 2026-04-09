from __future__ import annotations

import pandas as pd

from backend.repositories.portfolios import create_portfolio, get_portfolio_for_user
from backend.services.import_service import import_transactions_dataframe
from backend.services.market_data_service import load_market_data
from backend.services.portfolio_service import calculate_net_invested_capital, load_portfolio_transactions_dataframe


def create_rebalance_portfolio(
    *,
    user_id,
    source_portfolio_id,
    portfolio_name,
    rebalance_rows,
    derived_from,
):
    if not user_id:
        raise ValueError("Authentication is required.")
    if not source_portfolio_id:
        raise ValueError("An active source portfolio is required.")

    source_portfolio = get_portfolio_for_user(user_id, source_portfolio_id)
    if not source_portfolio:
        raise ValueError("The source portfolio could not be found.")

    source_df = load_portfolio_transactions_dataframe(user_id, source_portfolio_id, fallback=None)
    if source_df is None or source_df.empty:
        raise ValueError("The source portfolio has no transactions.")

    effective_start_date = _resolve_effective_start_date(source_df)
    allocations = _normalize_rebalance_rows(rebalance_rows)
    initial_capital = calculate_net_invested_capital(source_df)
    if initial_capital <= 0:
        raise ValueError("The source portfolio has no net invested capital to simulate.")

    simulated_df = _build_simulated_transactions(
        allocations=allocations,
        effective_start_date=effective_start_date,
        initial_capital=initial_capital,
    )

    name = (portfolio_name or "").strip() or _default_portfolio_name(source_portfolio["name"], derived_from)
    new_portfolio = create_portfolio(
        user_id=user_id,
        name=name,
        source_filename=f"derived:{derived_from}",
        source_portfolio_id=source_portfolio_id,
        derived_from=derived_from,
        effective_start_date=effective_start_date.date().isoformat(),
        baseline_invested_capital=initial_capital,
    )

    import_transactions_dataframe(
        portfolio_id=new_portfolio["id"],
        dataframe=simulated_df,
        filename=f"derived:{derived_from}:{source_portfolio['name']}",
    )
    return new_portfolio, simulated_df


def _default_portfolio_name(source_name, derived_from):
    suffix_map = {
        "rebalance_mv": "MV",
        "rebalance_rp": "RP",
        "rebalance_cvar": "CVaR",
    }
    suffix = suffix_map.get(derived_from, "Rebalance")
    return f"{source_name} {suffix}"


def _resolve_effective_start_date(dataframe: pd.DataFrame) -> pd.Timestamp:
    dates = pd.to_datetime(dataframe.get("Date"), errors="coerce", utc=True).dropna()
    if dates.empty:
        raise ValueError("The source portfolio has no valid transaction dates.")
    return dates.min().tz_convert(None).normalize()


def _normalize_rebalance_rows(rebalance_rows):
    if not rebalance_rows:
        raise ValueError("Generate a rebalance result before saving it.")

    normalized = {}
    for row in rebalance_rows:
        ticker = _clean_ticker(row.get("ticker"))
        try:
            weight = float(row.get("weight", 0))
        except (TypeError, ValueError):
            weight = 0.0
        if not ticker or weight < 0.01:
            continue
        normalized[ticker] = normalized.get(ticker, 0.0) + weight

    if not normalized:
        raise ValueError("The rebalance result does not contain any weights >= 0.01.")

    total_weight = sum(normalized.values())
    if total_weight <= 0:
        raise ValueError("The rebalance result has an invalid total weight.")

    return [
        {"ticker": ticker, "weight": weight / total_weight}
        for ticker, weight in normalized.items()
    ]


def _clean_ticker(value):
    if value is None:
        return None
    ticker = str(value).strip()
    if not ticker:
        return None
    return ticker.split(".")[0]


def _build_simulated_transactions(*, allocations, effective_start_date, initial_capital):
    market_data = load_market_data().copy()
    market_data["date"] = pd.to_datetime(market_data["date"], errors="coerce")
    market_data["Ticker_clean"] = market_data["Ticker"].astype(str).str.split(".").str[0]

    start_date_str = effective_start_date.strftime("%Y-%m-%dT00:00:00")
    records = [
        {
            "Date": start_date_str,
            "Ticker": None,
            "Type": "CASH TOP-UP",
            "Quantity": None,
            "Price per share": None,
            "Total Amount": f"{initial_capital:.2f}",
            "Currency": "EUR",
            "FX Rate": None,
        }
    ]

    remaining_amount = round(float(initial_capital), 2)
    for index, allocation in enumerate(allocations):
        ticker = allocation["ticker"]
        if index == len(allocations) - 1:
            amount = remaining_amount
        else:
            amount = round(float(initial_capital) * allocation["weight"], 2)
            remaining_amount = round(remaining_amount - amount, 2)

        price = _resolve_reference_price(market_data, ticker, effective_start_date)
        quantity = round(amount / price, 8) if price > 0 else round(amount, 8)
        records.append(
            {
                "Date": start_date_str,
                "Ticker": ticker,
                "Type": "BUY - MARKET",
                "Quantity": quantity,
                "Price per share": f"{price:.6f}",
                "Total Amount": f"{amount:.2f}",
                "Currency": "EUR",
                "FX Rate": None,
            }
        )

    return pd.DataFrame(records)


def _resolve_reference_price(market_data: pd.DataFrame, ticker: str, effective_start_date: pd.Timestamp) -> float:
    ticker_rows = market_data.loc[market_data["Ticker_clean"] == ticker].copy()
    if ticker_rows.empty:
        return 1.0

    before = ticker_rows.loc[ticker_rows["date"] <= effective_start_date].sort_values("date")
    if not before.empty:
        return float(before.iloc[-1]["adjusted_close"])

    after = ticker_rows.loc[ticker_rows["date"] >= effective_start_date].sort_values("date")
    if not after.empty:
        return float(after.iloc[0]["adjusted_close"])

    return float(ticker_rows.sort_values("date").iloc[0]["adjusted_close"])
