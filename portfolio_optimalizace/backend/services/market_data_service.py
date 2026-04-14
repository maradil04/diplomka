import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

from backend.repositories.market_prices import (
    acquire_download_lock,
    clear_stale_download_locks,
    get_download_lock,
    list_market_price_rows,
    market_price_coverage,
    release_download_lock,
    upsert_market_price_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

DEFAULT_PROVIDER = "eodhd"
DEFAULT_EXCHANGE = os.getenv("MARKET_DATA_DEFAULT_EXCHANGE", "XETRA").strip().upper() or "XETRA"
DEFAULT_STALENESS_DAYS = int(os.getenv("MARKET_DATA_MAX_STALENESS_DAYS", "7"))
DOWNLOAD_LOCK_STALE_SECONDS = int(os.getenv("MARKET_DATA_DOWNLOAD_LOCK_STALE_SECONDS", "300"))
DOWNLOAD_LOCK_WAIT_SECONDS = float(os.getenv("MARKET_DATA_DOWNLOAD_LOCK_WAIT_SECONDS", "15"))
DOWNLOAD_LOCK_POLL_SECONDS = float(os.getenv("MARKET_DATA_DOWNLOAD_LOCK_POLL_SECONDS", "0.5"))

_MARKET_DATA_CACHE = {}


def invalidate_market_data_cache():
    _MARKET_DATA_CACHE.clear()


def normalize_portfolio_ticker(value):
    ticker = str(value or "").strip().upper()
    if not ticker:
        return None
    return ticker.split(".", 1)[0]


def provider_ticker_from_portfolio_ticker(value, default_exchange=DEFAULT_EXCHANGE):
    ticker = normalize_portfolio_ticker(value)
    if not ticker:
        return None
    if "." in str(value or "").strip():
        return str(value).strip().upper()
    return f"{ticker}.{default_exchange}"


def extract_portfolio_tickers(dataframe: pd.DataFrame):
    if not isinstance(dataframe, pd.DataFrame) or "Ticker" not in dataframe.columns:
        return []
    tickers = {
        normalize_portfolio_ticker(value)
        for value in dataframe["Ticker"].dropna().tolist()
    }
    return sorted(ticker for ticker in tickers if ticker)


def _cache_key(*, tickers=None, start_date=None, end_date=None):
    normalized_tickers = tuple(sorted(str(ticker).upper() for ticker in (tickers or []) if ticker))
    return normalized_tickers, str(start_date or ""), str(end_date or "")


def _fallback_market_data(*, tickers=None, start_date=None, end_date=None):
    csv_path = PROJECT_ROOT / "df_prices.csv"
    if not csv_path.exists():
        return pd.DataFrame(columns=["date", "Ticker", "Ticker_clean", "adjusted_close"])

    dataframe = pd.read_csv(csv_path)
    if "date" in dataframe.columns:
        dataframe["date"] = pd.to_datetime(dataframe["date"], errors="coerce").dt.date
    if "Ticker" not in dataframe.columns:
        dataframe["Ticker"] = None
    dataframe["Ticker_clean"] = dataframe["Ticker"].astype(str).str.split(".").str[0]

    if tickers:
        clean = {normalize_portfolio_ticker(ticker) for ticker in tickers}
        dataframe = dataframe[dataframe["Ticker_clean"].isin(clean)]
    if start_date is not None and "date" in dataframe.columns:
        dataframe = dataframe[dataframe["date"] >= start_date]
    if end_date is not None and "date" in dataframe.columns:
        dataframe = dataframe[dataframe["date"] <= end_date]
    return dataframe.reset_index(drop=True)


def _seed_market_data_from_fallback_csv(provider_tickers):
    dataframe = _fallback_market_data()
    if dataframe.empty or "Ticker" not in dataframe.columns:
        return []

    rows = []
    filtered = dataframe[dataframe["Ticker"].isin(provider_tickers)].copy()
    if filtered.empty:
        return rows

    for item in filtered.to_dict("records"):
        price_date = pd.to_datetime(item.get("date"), errors="coerce")
        if pd.isna(price_date):
            continue
        rows.append(
            {
                "ticker": item.get("Ticker"),
                "date": price_date.date(),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": item.get("close"),
                "adjusted_close": item.get("adjusted_close", item.get("close")),
                "volume": item.get("volume"),
                "exchange": item.get("exchange") or (str(item.get("Ticker")).split(".", 1)[1] if "." in str(item.get("Ticker")) else DEFAULT_EXCHANGE),
                "currency": item.get("currency"),
                "provider": item.get("provider") or "csv_seed",
            }
        )
    if rows:
        upsert_market_price_rows(rows)
        invalidate_market_data_cache()
    return rows


def load_market_data(*, tickers=None, start_date=None, end_date=None, use_cache=True) -> pd.DataFrame:
    cache_key = _cache_key(tickers=tickers, start_date=start_date, end_date=end_date)
    if use_cache and cache_key in _MARKET_DATA_CACHE:
        return _MARKET_DATA_CACHE[cache_key].copy()

    provider_tickers = None
    if tickers:
        provider_tickers = [
            provider_ticker_from_portfolio_ticker(ticker)
            for ticker in tickers
            if provider_ticker_from_portfolio_ticker(ticker)
        ]

    try:
        rows = list_market_price_rows(tickers=provider_tickers, start_date=start_date, end_date=end_date)
    except (RuntimeError, psycopg.Error):
        rows = []

    if rows:
        dataframe = pd.DataFrame(rows)
        dataframe["date"] = pd.to_datetime(dataframe["date"], errors="coerce")
        dataframe["Ticker"] = dataframe["ticker"].astype(str)
        dataframe["Ticker_clean"] = dataframe["Ticker"].str.split(".").str[0]
        dataframe["adjusted_close"] = pd.to_numeric(dataframe["adjusted_close"], errors="coerce")
        dataframe = dataframe.sort_values(["Ticker", "date"]).reset_index(drop=True)
    else:
        dataframe = _fallback_market_data(tickers=tickers, start_date=start_date, end_date=end_date)
        if "date" in dataframe.columns:
            dataframe["date"] = pd.to_datetime(dataframe["date"], errors="coerce")

    if use_cache:
        _MARKET_DATA_CACHE[cache_key] = dataframe.copy()
    return dataframe


def _get_api_token():
    token = os.getenv("EODHD_API_TOKEN") or os.getenv("EOD_API_TOKEN")
    token = (token or "").strip()
    if not token:
        raise RuntimeError("Missing EODHD_API_TOKEN for market data download.")
    return token


def _is_ticker_stale(provider_ticker, coverage, stale_cutoff):
    info = coverage.get(provider_ticker)
    max_date = info.get("max_date") if info else None
    return max_date is None or max_date < stale_cutoff


def _wait_for_other_download(provider_ticker, stale_cutoff):
    deadline = time.monotonic() + max(DOWNLOAD_LOCK_WAIT_SECONDS, 0.0)
    while time.monotonic() < deadline:
        time.sleep(max(DOWNLOAD_LOCK_POLL_SECONDS, 0.1))
        coverage = market_price_coverage(tickers=[provider_ticker])
        if not _is_ticker_stale(provider_ticker, coverage, stale_cutoff):
            return coverage, True

        lock_row = get_download_lock(provider_ticker)
        if not lock_row:
            return coverage, False

    coverage = market_price_coverage(tickers=[provider_ticker])
    return coverage, not _is_ticker_stale(provider_ticker, coverage, stale_cutoff)


def _download_ticker_with_lock(provider_ticker, stale_cutoff):
    clear_stale_download_locks(older_than_seconds=DOWNLOAD_LOCK_STALE_SECONDS)

    coverage = market_price_coverage(tickers=[provider_ticker])
    if not _is_ticker_stale(provider_ticker, coverage, stale_cutoff):
        return False, coverage

    if acquire_download_lock(provider_ticker):
        try:
            coverage = market_price_coverage(tickers=[provider_ticker])
            if _is_ticker_stale(provider_ticker, coverage, stale_cutoff):
                rows = _fetch_eodhd_rows(provider_ticker)
                upsert_market_price_rows(rows)
                invalidate_market_data_cache()
            coverage = market_price_coverage(tickers=[provider_ticker])
            return True, coverage
        finally:
            release_download_lock(provider_ticker)

    coverage, completed_by_other = _wait_for_other_download(provider_ticker, stale_cutoff)
    if completed_by_other:
        return False, coverage

    clear_stale_download_locks(older_than_seconds=DOWNLOAD_LOCK_STALE_SECONDS)
    if acquire_download_lock(provider_ticker):
        try:
            coverage = market_price_coverage(tickers=[provider_ticker])
            if _is_ticker_stale(provider_ticker, coverage, stale_cutoff):
                rows = _fetch_eodhd_rows(provider_ticker)
                upsert_market_price_rows(rows)
                invalidate_market_data_cache()
            coverage = market_price_coverage(tickers=[provider_ticker])
            return True, coverage
        finally:
            release_download_lock(provider_ticker)

    coverage = market_price_coverage(tickers=[provider_ticker])
    return False, coverage


def _fetch_eodhd_rows(provider_ticker):
    params = urllib.parse.urlencode({"api_token": _get_api_token(), "fmt": "json"})
    url = f"https://eodhistoricaldata.com/api/eod/{provider_ticker}?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "portfolio-optimalizace/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Market data download failed for {provider_ticker}: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Market data download failed for {provider_ticker}: {exc.reason}") from exc

    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected market data response for {provider_ticker}.")

    exchange = provider_ticker.split(".", 1)[1] if "." in provider_ticker else DEFAULT_EXCHANGE
    rows = []
    for item in payload:
        price_date = pd.to_datetime(item.get("date"), errors="coerce")
        if pd.isna(price_date):
            continue
        rows.append(
            {
                "ticker": provider_ticker,
                "date": price_date.date(),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": item.get("close"),
                "adjusted_close": item.get("adjusted_close", item.get("close")),
                "volume": item.get("volume"),
                "exchange": exchange,
                "currency": item.get("currency"),
                "provider": DEFAULT_PROVIDER,
            }
        )
    return rows


def ensure_market_data_for_tickers(*, tickers, max_staleness_days=DEFAULT_STALENESS_DAYS):
    clean_tickers = sorted({normalize_portfolio_ticker(ticker) for ticker in (tickers or []) if normalize_portfolio_ticker(ticker)})
    if not clean_tickers:
        return {
            "requested_tickers": [],
            "provider_tickers": [],
            "downloaded_tickers": [],
            "overlap_start": None,
            "overlap_end": None,
            "coverage": {},
        }

    provider_map = {
        ticker: provider_ticker_from_portfolio_ticker(ticker)
        for ticker in clean_tickers
    }
    provider_tickers = [ticker for ticker in provider_map.values() if ticker]
    coverage = market_price_coverage(tickers=provider_tickers)

    missing_provider_tickers = [ticker for ticker in provider_tickers if ticker not in coverage]
    if missing_provider_tickers:
        _seed_market_data_from_fallback_csv(missing_provider_tickers)
        coverage = market_price_coverage(tickers=provider_tickers)

    stale_cutoff = date.today() - timedelta(days=max_staleness_days)
    stale_provider_tickers = []
    for provider_ticker in provider_tickers:
        if _is_ticker_stale(provider_ticker, coverage, stale_cutoff):
            stale_provider_tickers.append(provider_ticker)

    downloaded_tickers = []
    for provider_ticker in stale_provider_tickers:
        downloaded, ticker_coverage = _download_ticker_with_lock(provider_ticker, stale_cutoff)
        if downloaded:
            downloaded_tickers.append(provider_ticker)
        coverage.update(ticker_coverage)

    min_dates = []
    max_dates = []
    for provider_ticker in provider_tickers:
        info = coverage.get(provider_ticker)
        if not info:
            continue
        if info.get("min_date") is not None:
            min_dates.append(info["min_date"])
        if info.get("max_date") is not None:
            max_dates.append(info["max_date"])

    overlap_start = max(min_dates) if min_dates else None
    overlap_end = min(max_dates) if max_dates else None

    return {
        "requested_tickers": clean_tickers,
        "provider_tickers": provider_tickers,
        "downloaded_tickers": downloaded_tickers,
        "overlap_start": overlap_start,
        "overlap_end": overlap_end,
        "coverage": coverage,
    }


def ensure_market_data_for_portfolio_dataframe(dataframe: pd.DataFrame, max_staleness_days=DEFAULT_STALENESS_DAYS):
    tickers = extract_portfolio_tickers(dataframe)
    return ensure_market_data_for_tickers(tickers=tickers, max_staleness_days=max_staleness_days)
