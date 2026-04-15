import numpy as np
import pandas as pd


def _to_naive_datetime_series(series):
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()


def portfolio_tickers(dataframe: pd.DataFrame):
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty or "Ticker" not in dataframe.columns:
        return []
    return (
        dataframe["Ticker"]
        .dropna()
        .astype(str)
        .str.split(".")
        .str[0]
        .dropna()
        .unique()
        .tolist()
    )


def build_portfolio_value_history(dataframe: pd.DataFrame, price_dataframe: pd.DataFrame) -> pd.DataFrame:
    trades = _prepare_trade_holdings(dataframe)
    if trades.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])

    prices = _prepare_prices(price_dataframe)
    if prices.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])

    aligned_prices = _build_aligned_price_panel(prices)
    merged_parts = []
    for ticker, price_group in aligned_prices.groupby("Ticker_clean", sort=False):
        holdings = trades.loc[trades["Ticker"] == ticker, ["Date", "CumulativeShares"]].copy()
        if holdings.empty:
            continue
        price_group = price_group.sort_values("date").copy()
        merged = pd.merge_asof(
            price_group,
            holdings.sort_values("Date"),
            left_on="date",
            right_on="Date",
            direction="backward",
        )
        merged["Ticker_clean"] = ticker
        merged["CumulativeShares"] = merged["CumulativeShares"].fillna(0.0)
        merged_parts.append(merged)

    if not merged_parts:
        return pd.DataFrame(columns=["date", "portfolio_value"])

    final = pd.concat(merged_parts, ignore_index=True)
    final["position_value"] = final["CumulativeShares"] * final["adjusted_close"]
    by_day = (
        final.groupby("date", as_index=False)["position_value"]
        .sum()
        .rename(columns={"position_value": "portfolio_value"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    by_day = by_day[by_day["portfolio_value"] > 0]
    return by_day


def build_position_history(dataframe: pd.DataFrame, price_dataframe: pd.DataFrame) -> pd.DataFrame:
    trades = _prepare_trade_holdings(dataframe)
    if trades.empty:
        return pd.DataFrame()

    prices = _prepare_prices(price_dataframe)
    if prices.empty:
        return pd.DataFrame()

    aligned_prices = _build_aligned_price_panel(prices)
    merged_parts = []
    for ticker, price_group in aligned_prices.groupby("Ticker_clean", sort=False):
        holdings = trades.loc[trades["Ticker"] == ticker, ["Date", "CumulativeShares"]].copy()
        if holdings.empty:
            continue
        merged = pd.merge_asof(
            price_group.sort_values("date"),
            holdings.sort_values("Date"),
            left_on="date",
            right_on="Date",
            direction="backward",
        )
        merged["Ticker_clean"] = ticker
        merged["CumulativeShares"] = merged["CumulativeShares"].fillna(0.0)
        merged["position_value"] = merged["CumulativeShares"] * merged["adjusted_close"]
        merged_parts.append(merged)

    if not merged_parts:
        return pd.DataFrame()

    final = pd.concat(merged_parts, ignore_index=True).sort_values(["Ticker_clean", "date"])
    final["portfolio_value"] = final.groupby("date")["position_value"].transform("sum")
    return final.reset_index(drop=True)


def _prepare_trade_holdings(dataframe: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        return pd.DataFrame(columns=["Date", "Ticker", "CumulativeShares"])

    trades = dataframe.copy()
    if "Type" not in trades.columns or "Ticker" not in trades.columns:
        return pd.DataFrame(columns=["Date", "Ticker", "CumulativeShares"])

    trades = trades[trades["Type"].isin(["BUY - MARKET", "SELL - MARKET"])].copy()
    if trades.empty:
        return pd.DataFrame(columns=["Date", "Ticker", "CumulativeShares"])

    trades["Date"] = _to_naive_datetime_series(trades["Date"])
    trades["Ticker"] = trades["Ticker"].astype(str).str.split(".").str[0]
    trades["Quantity"] = pd.to_numeric(trades.get("Quantity"), errors="coerce").fillna(0.0)
    trades["SignedQuantity"] = np.where(trades["Type"].eq("SELL - MARKET"), -trades["Quantity"], trades["Quantity"])

    daily = (
        trades.dropna(subset=["Date", "Ticker"])
        .groupby(["Ticker", "Date"], as_index=False)["SignedQuantity"]
        .sum()
        .sort_values(["Ticker", "Date"])
    )
    daily["CumulativeShares"] = daily.groupby("Ticker", sort=False)["SignedQuantity"].cumsum()
    return daily[["Date", "Ticker", "CumulativeShares"]]


def _prepare_prices(price_dataframe: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(price_dataframe, pd.DataFrame) or price_dataframe.empty:
        return pd.DataFrame(columns=["date", "Ticker_clean", "adjusted_close"])

    prices = price_dataframe.copy()
    prices["date"] = _to_naive_datetime_series(prices["date"])
    if "Ticker_clean" not in prices.columns:
        prices["Ticker_clean"] = prices["Ticker"].astype(str).str.split(".").str[0]
    prices["adjusted_close"] = pd.to_numeric(prices["adjusted_close"], errors="coerce")
    prices = prices.dropna(subset=["date", "Ticker_clean", "adjusted_close"])
    prices = prices.sort_values(["Ticker_clean", "date"]).drop_duplicates(subset=["Ticker_clean", "date"])
    return prices[["date", "Ticker_clean", "adjusted_close"]]


def _build_aligned_price_panel(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        return pd.DataFrame(columns=["date", "Ticker_clean", "adjusted_close"])

    master_dates = pd.Index(sorted(prices["date"].dropna().unique()), name="date")
    if master_dates.empty:
        return pd.DataFrame(columns=["date", "Ticker_clean", "adjusted_close"])

    aligned_parts = []
    for ticker, price_group in prices.groupby("Ticker_clean", sort=False):
        indexed = (
            price_group[["date", "adjusted_close"]]
            .drop_duplicates(subset=["date"])
            .set_index("date")
            .sort_index()
        )
        aligned = indexed.reindex(master_dates).ffill()
        aligned = aligned.dropna(subset=["adjusted_close"]).reset_index()
        aligned["Ticker_clean"] = ticker
        aligned_parts.append(aligned[["date", "Ticker_clean", "adjusted_close"]])

    if not aligned_parts:
        return pd.DataFrame(columns=["date", "Ticker_clean", "adjusted_close"])

    return pd.concat(aligned_parts, ignore_index=True).sort_values(["Ticker_clean", "date"]).reset_index(drop=True)
