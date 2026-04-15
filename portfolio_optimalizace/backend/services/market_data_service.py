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
import yfinance as yf
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
from backend.repositories.ticker_mappings import get_ticker_mapping, upsert_ticker_mapping


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
_YAHOO_SUFFIX_TO_EODHD = {
    "AS": "AS",
    "DE": "XETRA",
    "F": "FRA",
    "HK": "HK",
    "L": "LSE",
    "MI": "MI",
    "PA": "PA",
    "PR": "PR",
    "SW": "SW",
    "T": "TSE",
    "TO": "TO",
    "V": "VI",
}
_YAHOO_EXCHANGE_TO_EODHD = {
    "NASDAQ": "US",
    "NYSE": "US",
    "NYSEARCA": "US",
    "NYSE AMERICAN": "US",
    "OTC MARKETS": "US",
    "SWISS": "SW",
    "SIX": "SW",
    "PARIS": "PA",
    "EURONEXT PARIS": "PA",
    "AMSTERDAM": "AS",
    "EURONEXT AMSTERDAM": "AS",
    "FRANKFURT": "FRA",
    "XETRA": "XETRA",
    "PRAGUE": "PR",
    "PRAGUE STOCK EXCHANGE": "PR",
    "TOKYO": "TSE",
    "TOKYO STOCK EXCHANGE": "TSE",
    "HONG KONG": "HK",
    "LONDON": "LSE",
    "MILAN": "MI",
    "TORONTO": "TO",
    "VIENNA": "VI",
}


def invalidate_market_data_cache():
    _MARKET_DATA_CACHE.clear()


def normalize_input_ticker(value):
    ticker = str(value or "").strip().upper()
    if not ticker:
        return None
    return ticker


def normalize_portfolio_ticker(value):
    ticker = normalize_input_ticker(value)
    if not ticker:
        return None
    return ticker.split(".", 1)[0]


def provider_ticker_from_portfolio_ticker(value, default_exchange=DEFAULT_EXCHANGE):
    resolved = resolve_provider_ticker(value, default_exchange=default_exchange)
    return resolved["provider_ticker"] if resolved else None


def extract_portfolio_tickers(dataframe: pd.DataFrame):
    if not isinstance(dataframe, pd.DataFrame) or "Ticker" not in dataframe.columns:
        return []
    tickers = {
        normalize_input_ticker(value)
        for value in dataframe["Ticker"].dropna().tolist()
    }
    return sorted(ticker for ticker in tickers if ticker)


def _cache_key(*, tickers=None, start_date=None, end_date=None):
    normalized_tickers = tuple(sorted(normalize_input_ticker(ticker) for ticker in (tickers or []) if normalize_input_ticker(ticker)))
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
        provider_tickers = []
        for ticker in tickers:
            resolved = resolve_provider_ticker(ticker)
            if resolved and resolved.get("provider_ticker"):
                provider_tickers.append(resolved["provider_ticker"])

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


def _mapping_payload(*, input_ticker, provider_ticker, exchange=None, currency=None, resolution_source="manual", confirmed=True):
    return {
        "input_ticker": input_ticker,
        "provider_ticker": provider_ticker,
        "exchange": exchange,
        "currency": currency,
        "resolution_source": resolution_source,
        "confirmed": confirmed,
    }


def _cache_mapping(*, input_ticker, provider_ticker, exchange=None, currency=None, resolution_source="manual", confirmed=True, mirror_clean_ticker=False):
    payload = _mapping_payload(
        input_ticker=input_ticker,
        provider_ticker=provider_ticker,
        exchange=exchange,
        currency=currency,
        resolution_source=resolution_source,
        confirmed=confirmed,
    )
    upsert_ticker_mapping(**payload)
    if mirror_clean_ticker:
        clean_ticker = normalize_portfolio_ticker(input_ticker)
        if clean_ticker and clean_ticker != input_ticker and not get_ticker_mapping(clean_ticker):
            upsert_ticker_mapping(
                input_ticker=clean_ticker,
                provider_ticker=provider_ticker,
                exchange=exchange,
                currency=currency,
                resolution_source=resolution_source,
                confirmed=confirmed,
            )
    return payload


def _exchange_from_provider_ticker(provider_ticker):
    return provider_ticker.split(".", 1)[1] if "." in provider_ticker else DEFAULT_EXCHANGE


def _provider_ticker_from_yahoo_quote(quote):
    symbol = str(quote.get("symbol") or "").upper().strip()
    if not symbol:
        return None

    if "." in symbol:
        base_symbol, yahoo_suffix = symbol.rsplit(".", 1)
        mapped_suffix = _YAHOO_SUFFIX_TO_EODHD.get(yahoo_suffix.upper())
        if mapped_suffix:
            return f"{base_symbol}.{mapped_suffix}"

    exchange_name = str(quote.get("exchDisp") or quote.get("exchangeDisp") or quote.get("exchange") or "").upper().strip()
    mapped_exchange = _YAHOO_EXCHANGE_TO_EODHD.get(exchange_name)
    if mapped_exchange:
        return f"{symbol.split('.', 1)[0]}.{mapped_exchange}"

    if quote.get("quoteType") in {"EQUITY", "ETF", "MUTUALFUND"}:
        return f"{symbol.split('.', 1)[0]}.US"
    return None


def _resolve_provider_ticker_via_yfinance(input_ticker):
    try:
        search = yf.Search(input_ticker, max_results=8, news_count=0, lists_count=0, include_cb=False, raise_errors=False)
    except Exception:
        return None

    quotes = getattr(search, "quotes", None) or []
    if not quotes:
        return None

    clean_input = normalize_portfolio_ticker(input_ticker)
    candidates = []
    for quote in quotes:
        quote_type = str(quote.get("quoteType") or "").upper()
        if quote_type not in {"EQUITY", "ETF", "MUTUALFUND"}:
            continue
        provider_ticker = _provider_ticker_from_yahoo_quote(quote)
        if not provider_ticker:
            continue
        symbol = str(quote.get("symbol") or "").upper()
        score = 0
        if symbol.split(".", 1)[0] == clean_input:
            score += 10
        if symbol == clean_input:
            score += 3
        if quote_type == "ETF":
            score += 1
        candidates.append((score, quote, provider_ticker))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    _score, quote, provider_ticker = candidates[0]
    return _mapping_payload(
        input_ticker=normalize_input_ticker(input_ticker),
        provider_ticker=provider_ticker,
        exchange=_exchange_from_provider_ticker(provider_ticker),
        currency=quote.get("currency"),
        resolution_source="yfinance",
        confirmed=False,
    )


def resolve_provider_ticker(value, default_exchange=DEFAULT_EXCHANGE):
    input_ticker = normalize_input_ticker(value)
    if not input_ticker:
        return None

    if "." in input_ticker:
        provider_ticker = input_ticker
        return _cache_mapping(
            input_ticker=input_ticker,
            provider_ticker=provider_ticker,
            exchange=_exchange_from_provider_ticker(provider_ticker),
            resolution_source="direct_input",
            confirmed=True,
            mirror_clean_ticker=True,
        )

    existing = get_ticker_mapping(input_ticker)
    if existing:
        return existing

    fallback = _resolve_provider_ticker_via_yfinance(input_ticker)
    if fallback:
        return _cache_mapping(
            input_ticker=input_ticker,
            provider_ticker=fallback["provider_ticker"],
            exchange=fallback.get("exchange"),
            currency=fallback.get("currency"),
            resolution_source="yfinance",
            confirmed=False,
        )

    provider_ticker = f"{input_ticker}.{default_exchange}"
    return _cache_mapping(
        input_ticker=input_ticker,
        provider_ticker=provider_ticker,
        exchange=default_exchange,
        resolution_source="default_exchange",
        confirmed=False,
    )


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
    input_tickers = sorted({normalize_input_ticker(ticker) for ticker in (tickers or []) if normalize_input_ticker(ticker)})
    if not input_tickers:
        return {
            "requested_tickers": [],
            "provider_tickers": [],
            "downloaded_tickers": [],
            "overlap_start": None,
            "overlap_end": None,
            "coverage": {},
        }

    resolved_mappings = {}
    provider_tickers = []
    for ticker in input_tickers:
        resolved = resolve_provider_ticker(ticker)
        if not resolved or not resolved.get("provider_ticker"):
            continue
        resolved_mappings[ticker] = resolved
        provider_tickers.append(resolved["provider_ticker"])

    provider_tickers = sorted(set(provider_tickers))
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
        "requested_tickers": input_tickers,
        "provider_tickers": provider_tickers,
        "resolved_mappings": resolved_mappings,
        "downloaded_tickers": downloaded_tickers,
        "overlap_start": overlap_start,
        "overlap_end": overlap_end,
        "coverage": coverage,
    }


def ensure_market_data_for_portfolio_dataframe(dataframe: pd.DataFrame, max_staleness_days=DEFAULT_STALENESS_DAYS):
    tickers = extract_portfolio_tickers(dataframe)
    return ensure_market_data_for_tickers(tickers=tickers, max_staleness_days=max_staleness_days)
