from dash import register_page, html, dcc, dash_table, no_update
from dash import Input, Output, State, MATCH
import pandas as pd
import plotly.express as px
from datetime import date
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import io, base64
from threading import Lock
import dash
app = dash.get_app()

from backend.services.import_service import import_transactions_dataframe, parse_upload_contents
from backend.repositories.portfolios import get_portfolio_for_user
from backend.services.market_data_service import (
    ensure_market_data_for_portfolio_dataframe,
    load_market_data,
)
from backend.services.portfolio_service import (
    calculate_net_invested_capital,
    empty_transactions_dataframe,
    list_user_portfolios,
    load_portfolio_transactions_dataframe,
)
from backend.session import get_current_user
from utils.portfolio_history import build_portfolio_value_history, build_position_history, portfolio_tickers
from utils.i18n import normalize_language, t

register_page(__name__, path="/dashboard")
#--------------- Načítání dat
df_empty = empty_transactions_dataframe()
df_prices = load_market_data().copy()
df_prices_all = load_market_data().copy()
df_prices["Ticker_clean"] = df_prices["Ticker"].str.split(".").str[0]
df_prices_all = df_prices.copy()
tickers_all = sorted(set(df_prices["Ticker_clean"]))
tickers_default = ['SXR8']
tickers_l = []
tickers_l_default = []
#---------------


def _portfolio_id_from_state(active_portfolio_data):
    if not isinstance(active_portfolio_data, dict):
        return None
    portfolio_id = active_portfolio_data.get("portfolio_id")
    if portfolio_id in (None, ""):
        return None
    try:
        return int(portfolio_id)
    except (TypeError, ValueError):
        return None


def _get_current_portfolio_df(active_portfolio_data):
    user = get_current_user()
    portfolio_id = _portfolio_id_from_state(active_portfolio_data)
    if user and portfolio_id:
        loaded = load_portfolio_transactions_dataframe(user["id"], portfolio_id, fallback=df_empty)
        return loaded.copy() if isinstance(loaded, pd.DataFrame) else df_empty.copy()
    return df_empty.copy()


def _get_portfolio_prices(dataframe=None):
    tickers = portfolio_tickers(dataframe) if isinstance(dataframe, pd.DataFrame) else []
    if tickers:
        return load_market_data(tickers=tickers, use_cache=False).copy()
    return load_market_data(use_cache=False).copy()


def _has_transaction_data(df):
    required = {"Date", "Type"}
    return isinstance(df, pd.DataFrame) and not df.empty and required.issubset(set(df.columns))


def _show_waiting_state(active_portfolio_data):
    portfolio_id = _portfolio_id_from_state(active_portfolio_data)
    if not portfolio_id:
        return False
    df = _get_current_portfolio_df(active_portfolio_data)
    return not _has_transaction_data(df)




def _to_naive_ts(x):
    """Scalar → tz-naive pd.Timestamp normalizovaný na půlnoc."""
    ts = pd.to_datetime(x, utc=True)
    return ts.tz_convert(None).normalize()
def _to_naive_day(s):
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None).dt.floor("D")

def _to_naive_series(s):
    """Series → tz-naive datetime64[ns] normalizovaný na půlnoc."""
    s = pd.to_datetime(s, errors="coerce", utc=True)
    return s.dt.tz_convert(None).dt.normalize()

def _force_naive_series(s):
    s = pd.to_datetime(s, errors="coerce", utc=True)
    s = s.dt.tz_convert(None)       
    return s.dt.normalize()

def _force_naive_scalar(ts):
    ts = pd.to_datetime(ts, errors="coerce", utc=True)
    return ts.tz_convert(None).normalize() if pd.notna(ts) else pd.NaT

def _parse_money_series(series):
    s = series.fillna("").astype(str).str.strip()
    s = s.str.replace("\u00A0", "", regex=False).str.replace(" ", "", regex=False)
    s = s.str.replace("€", "", regex=False).str.replace("â‚¬", "", regex=False)
    has_comma = s.str.contains(",", regex=False)
    has_dot = s.str.contains(".", regex=False)
    s = s.where(~(has_comma & ~has_dot), s.str.replace(",", ".", regex=False))
    s = s.where(~(has_comma & has_dot), s.str.replace(",", "", regex=False))
    s = s.str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def _format_numeric_display(value, *, decimals=2, suffix="", trim_trailing=False):
    if pd.isna(value):
        return "-"
    number = float(value)
    text = f"{number:,.{decimals}f}".replace(",", " ")
    if trim_trailing and "." in text:
        text = text.rstrip("0").rstrip(".")
    if suffix:
        text = f"{text} {suffix}"
    return text


def _home_frequency_options(language):
    lang = normalize_language(language)
    return [
        {"label": t(lang, "home.frequency.daily"), "value": "Daily"},
        {"label": t(lang, "home.frequency.monthly"), "value": "Monthly"},
    ]


def _build_dashboard_section(section_id, title, children):
    return html.Div(
        className="dashboard-section",
        children=[
            html.Button(
                id={"type": "dashboard-section-toggle", "index": section_id},
                className="dashboard-section-toggle",
                n_clicks=0,
                children=[
                    html.Span(title, id=f"dashboard-section-title-{section_id}", className="dashboard-section-title"),
                    html.Span(
                        "▾",
                        id={"type": "dashboard-section-arrow", "index": section_id},
                        className="dashboard-section-arrow",
                    ),
                ],
            ),
            html.Div(
                id={"type": "dashboard-section-content", "index": section_id},
                className="dashboard-section-content",
                children=[
                    html.Div(children, className="dashboard-section-content-inner"),
                ],
            ),
        ],
    )


def _hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    r, g, b = [max(0, min(255, int(round(channel)))) for channel in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"


def _interpolate_hex(start, end, steps):
    if steps <= 1:
        return [start]

    start_rgb = _hex_to_rgb(start)
    end_rgb = _hex_to_rgb(end)
    colors = []
    for idx in range(steps):
        ratio = idx / (steps - 1)
        rgb = tuple(
            start_rgb[channel] + (end_rgb[channel] - start_rgb[channel]) * ratio
            for channel in range(3)
        )
        colors.append(_rgb_to_hex(rgb))
    return colors


def _build_green_range():
    anchors = [
        "#c8ffd8",
        "#cfffaa",
        "#b8ffd2",
        "#c9ff9f",
        "#fff1b8",
        "#b7f06d",
        "#ffd37a",
        "#88f5b3",
        "#86d94d",
        "#ffb347",
        "#4fe08d",
        "#a1c93a",
        "#ff9433",
        "#00c878",
        "#65b82f",
        "#f27a1a",
        "#00a17b",
        "#3e9b28",
        "#cf6514",
        "#008f6b",
        "#2b7f2a",
        "#a95312",
        "#00785b",
        "#005f47",
        "#1f3b34",
        "#183126",
        "#0f241b",
    ]
    segments = []
    for index in range(len(anchors) - 1):
        segment = _interpolate_hex(anchors[index], anchors[index + 1], 7)
        if index:
            segment = segment[1:]
        segments.extend(segment)
    return segments


def _green_black_palette(count):
    gradient = _build_green_range()
    if count <= 0:
        return []
    if count == 1:
        return [gradient[len(gradient) // 2]]

    ordered_indexes = _max_separation_indexes(len(gradient))
    selected = [gradient[index] for index in ordered_indexes[:count]]
    return selected


def _max_separation_indexes(length):
    if length <= 0:
        return []

    ordered = []
    remaining = list(range(length))
    seed = [0, length - 1]
    for index in seed:
        if index in remaining:
            ordered.append(index)
            remaining.remove(index)

    if remaining:
        midpoint = (length - 1) / 2
        middle_index = min(remaining, key=lambda idx: abs(idx - midpoint))
        ordered.append(middle_index)
        remaining.remove(middle_index)

    while remaining:
        next_index = max(
            remaining,
            key=lambda idx: min(abs(idx - chosen) for chosen in ordered)
        )
        ordered.append(next_index)
        remaining.remove(next_index)

    return ordered


def _green_black_colorscale():
    anchors = [
        "#c8ffd8",
        "#cfffaa",
        "#b8ffd2",
        "#c9ff9f",
        "#fff1b8",
        "#88f5b3",
        "#86d94d",
        "#ffd37a",
        "#00c878",
        "#65b82f",
        "#ffb347",
        "#00a17b",
        "#f27a1a",
        "#00785b",
        "#a95312",
        "#1f3b34",
        "#183126",
        "#0f241b",
    ]
    max_index = max(len(anchors) - 1, 1)
    return [[idx / max_index, color] for idx, color in enumerate(anchors)]

def sjednoceni(target_date, data):
    target_date = pd.to_datetime(target_date, utc=True).tz_convert(None).normalize()

    df = data.copy()
    df["Date"] = (
        pd.to_datetime(df["Date"], errors="coerce", utc=True)
          .dt.tz_convert(None)
          .dt.normalize()
    )
    df = df[df["Date"] <= target_date]
    df = df[df["Ticker"].notna()]
    df = df[df["Type"].isin(["BUY - MARKET", "SELL - MARKET"])]
    amt = (df["Total Amount"].astype(str)
             .str.replace(r"[€\s\u00A0]", "", regex=True)
             .str.replace(",", "", regex=False))
    is_num = amt.str.match(r"^-?\d+(\.\d+)?$")
    df = df[is_num].copy()
    df["Total_clean"] = amt[is_num].astype(float)
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["Total_clean"] = np.where(df["Type"].eq("SELL - MARKET"),
                                 -df["Total_clean"], df["Total_clean"])
    df["Total_quant_clean"] = np.where(df["Type"].eq("SELL - MARKET"),
                                       -df["Quantity"], df["Quantity"])
    out = df.groupby("Ticker", as_index=False).agg(
        Total_value=("Total_clean", "sum"),
        Total_quantity=("Total_quant_clean", "sum"),
    )

    return out
def fees_divi(target_date,data):
    target_date = _force_naive_scalar(target_date)
    df_copy = data.copy()
    df_copy["Date"] = _to_naive_day(df_copy["Date"])
    df_copy = df_copy[df_copy["Date"] <= target_date]
    df_filtered = df_copy[df_copy["Type"].str.contains("FEE") | df_copy["Type"].str.contains("DIVIDEND")]
    df_filtered["Total_clean"] = (
        df_filtered["Total Amount"]
        .astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df_filtered = df_filtered[df_filtered["Total_clean"].str.match(r"^-?\d+(\.\d+)?$")]
    df_filtered["Total_clean"] = df_filtered["Total_clean"].astype(float)
    df_filtered["Total_clean"] = abs(df_filtered["Total_clean"])
    result = df_filtered.groupby("Type")["Total_clean"].sum().reset_index()
    result.columns = ["Type", "Total_money"]
    return result
def soucasna_cena(target_date, df_prices):
    target_date = _force_naive_scalar(target_date)
    df_copy = df_prices.copy()
    df_copy["date"] = _to_naive_day(df_copy["date"])
    df_copy = df_copy[df_copy["date"] <= target_date].copy()
    if df_copy.empty:
        return df_copy[["Ticker_clean", "adjusted_close"]]
    latest_by_ticker = df_copy.groupby("Ticker_clean")["date"].transform("max")
    df_copy = df_copy[df_copy["date"] == latest_by_ticker]
    return df_copy[["Ticker_clean", "adjusted_close"]]

def celkove_fee_divi(target_date, data):
    target_date = _force_naive_scalar(target_date)

    df = data.copy()
    df["Date"] = _to_naive_day(df["Date"])
    df = df[df["Date"] <= target_date]
    mask = df["Type"].str.contains("DIVIDEND", na=False) | df["Type"].str.contains("FEE", na=False)
    df = df[mask].copy()
    amt = (df["Total Amount"].fillna("")
             .astype(str)
             .str.replace(r"[€\s\u00A0]", "", regex=True)
             .str.replace(",", "", regex=False))
    is_num = amt.str.match(r"^-?\d+(\.\d+)?$")
    df = df[is_num].copy()
    df["Total_clean"] = amt[is_num].astype(float)
    is_fee = df["Type"].str.contains("FEE", na=False)
    is_div = df["Type"].str.contains("DIVIDEND", na=False)

    df.loc[is_fee, "Total_clean"] *= -1
    df["Ticker"] = df["Ticker"].fillna("__FEE__")
    result = (df.groupby("Ticker", as_index=False)["Total_clean"]
                .sum()
                .rename(columns={"Total_clean": "Total_money"}))

    return result

def vypocet_dividend(target_date, data):
    target_date = _force_naive_scalar(target_date)
    df_copy = data.copy()
    df_copy["Date"] = _to_naive_day(df_copy["Date"])
    df_copy = df_copy[df_copy["Date"] <= target_date]
    df_filtered = df_copy[df_copy["Type"].str.contains("DIVIDEND")]
    df_filtered["Total_clean"] = (
        df_filtered["Total Amount"]
        .fillna("")
        .astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df_filtered = df_filtered[df_filtered["Total_clean"].str.match(r"^-?\d+(\.\d+)?$")]
    df_filtered["Total_clean"] = df_filtered["Total_clean"].astype(float)
    result = df_filtered.groupby(["Ticker"])["Total_clean"].sum().reset_index()
    result.columns = ["Ticker", "Total_money"]
    return result
def hodnota_portfolia_v_case(target_date, df, df_prices):
    history = build_position_history(df, df_prices)
    if history.empty:
        return history
    target_date = pd.to_datetime(target_date, errors="coerce", utc=True)
    if pd.notna(target_date):
        target_date = target_date.tz_convert(None).normalize()
        history = history[history["date"] <= target_date]
    return history
def vypocitat_nevyuzity_kapital(target_date, df):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True).dt.tz_convert(None)
    df = df[df["Date"] <= target_date]
    df["Total_clean"] = _parse_money_series(df["Total Amount"]).fillna(0.0).abs()
    type_series = df["Type"].fillna("").astype(str)

    cash_topup = df.loc[type_series.eq("CASH TOP-UP"), "Total_clean"].sum()
    cash_withdrawal = df.loc[type_series.eq("CASH WITHDRAWAL"), "Total_clean"].sum()
    buys = df.loc[type_series.eq("BUY - MARKET"), "Total_clean"].sum()
    sells = df.loc[type_series.eq("SELL - MARKET"), "Total_clean"].sum()
    fees = df.loc[type_series.str.contains("FEE", na=False), "Total_clean"].sum()
    dividends = df.loc[type_series.str.contains("DIVIDEND", na=False), "Total_clean"].sum()

    estimated_free_cash = cash_topup - cash_withdrawal - buys + sells - fees + dividends
    return round(float(estimated_free_cash), 2)

def hodnota_portfolia_v_case_tabulka(target_date, df, df_prices):
    td = pd.to_datetime(target_date, errors="coerce", utc=True)
    td = td.tz_convert(None).normalize() if pd.notna(td) else pd.NaT
    by_day = build_portfolio_value_history(df, df_prices)
    if pd.notna(td):
        by_day = by_day[by_day["date"] <= td].reset_index(drop=True)
    return by_day

def investovany_kapital(target_date, df):
    return calculate_net_invested_capital(df, target_date=target_date)

def vypocet_flow(df):
    dfx = df.copy()

    amt = (dfx["Total Amount"].astype(str)
             .str.replace("€", "", regex=False)
             .str.replace(",", "", regex=False)
             .str.replace("-", "", regex=False))
    dfx["Total_clean"] = pd.to_numeric(amt, errors="coerce")
    dfx["Total_clean"] = np.where(dfx["Type"].eq("CASH WITHDRAWAL"),
                                 -dfx["Total_clean"], dfx["Total_clean"])

    operace = ["CASH WITHDRAWAL","CASH TOP-UP"]
    dfx = dfx[dfx["Type"].isin(operace)].copy()

    # --- NOVÉ: sjednocení datumu ---
    dfx["Date"] = _to_naive_day(dfx["Date"])

    return dfx[["Date","Type","Total_clean"]].reset_index(drop=True)


def hodnota_portfolia_bez_datumu(df, df_prices):
    return build_portfolio_value_history(df, df_prices)


def twr_index_from_df(
    df,
    df_prices,
    base: float = 100.0,
    price_date_col: str = "date",
    price_ticker_col: str = "Ticker_clean",
    price_close_col: str = "adjusted_close",
    trim_to_first_exposure: bool = True, 
):

    by_day = hodnota_portfolia_bez_datumu(df, df_prices)
    if by_day.empty:
        return pd.DataFrame(columns=["date", "portfolio_value", "flow", "twr_return", "twr_index"])

    out = by_day.copy()
    out["date"] = _to_naive_day(out["date"])
    out["portfolio_value"] = pd.to_numeric(out["portfolio_value"], errors="coerce").fillna(0.0)
    out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    flows_raw = vypocet_flow(df)
    if flows_raw is not None and not flows_raw.empty:
        fr = flows_raw.copy()
        fr["Date"] = _to_naive_day(fr["Date"])
        fr["Total_clean"] = pd.to_numeric(fr["Total_clean"], errors="coerce").fillna(0.0)
        flow_daily = (
            fr.groupby("Date", as_index=False)["Total_clean"]
              .sum()
              .rename(columns={"Total_clean": "flow"})
              .sort_values("Date")
        )
        pv_dates = out[["date"]].sort_values("date")
        mapped = pd.merge_asof(
            flow_daily, pv_dates,
            left_on="Date", right_on="date",
            direction="forward"
        ).dropna(subset=["date"])
        flow_on_pvday = mapped.groupby("date", as_index=False)["flow"].sum()
    else:
        flow_on_pvday = pd.DataFrame({"date": out["date"], "flow": 0.0})

    out = (out.merge(flow_on_pvday, on="date", how="left")
               .fillna({"flow": 0.0})
               .sort_values("date")
               .reset_index(drop=True))

    first_idx = int((out["portfolio_value"] > 0).idxmax()) if (out["portfolio_value"] > 0).any() else 0
    V0 = float(out.loc[first_idx, "portfolio_value"])
    F0 = float(out.loc[first_idx, "flow"])

    if V0 > 0:
        gap = V0 - F0
        if abs(gap) > max(1e-6, 1e-4 * V0):
            out.loc[first_idx, "flow"] += gap

    V = out["portfolio_value"].astype(float).values
    F = out["flow"].astype(float).values

    nav = np.empty_like(V, dtype=float)
    units = np.empty_like(V, dtype=float)

    if V[0] <= 0:
        nav_prev = 1.0
        units_prev = 0.0
    else:
        nav_prev = 1.0
        units_prev = V[0] / nav_prev

    nav[0] = nav_prev
    units[0] = units_prev

    for i in range(1, len(V)):
        if nav_prev == 0:
            nav_prev = 1.0
        units_i = units_prev + F[i] / nav_prev
        nav_i = 1.0 if units_i == 0 else V[i] / units_i
        units[i] = units_i
        nav[i] = nav_i
        units_prev, nav_prev = units_i, nav_i

    out["twr_return"] = pd.Series(nav).pct_change().fillna(0.0)
    out["twr_index"]  = base * (1.0 + out["twr_return"]).cumprod()

    if trim_to_first_exposure:
        pos_idx = np.argmax(units > 0)
        if units[pos_idx] > 0 and pos_idx > 0:
            out = out.iloc[pos_idx:].reset_index(drop=True)
            out["twr_index"] = base * out["twr_index"] / out["twr_index"].iloc[0]

    return out[["date","portfolio_value","flow","twr_return","twr_index"]]


def _resolve_summary_metrics(target_date, df, active_portfolio_data):
    tickers = set(portfolio_tickers(df))
    prices = _get_portfolio_prices(df).query("Ticker_clean in @tickers")
    by_day = hodnota_portfolia_v_case_tabulka(target_date, df, prices)

    if by_day.empty:
        pv = 0.0
        capital_free = float(vypocitat_nevyuzity_kapital(target_date, df))
        portfolio_value_total = round(pv + capital_free, 2)
    else:
        by_day["date"] = pd.to_datetime(by_day["date"], utc=True).dt.tz_convert(None).dt.normalize()
        last_date = by_day["date"].max()
        pv = float(by_day.loc[by_day["date"].eq(last_date), "portfolio_value"].iloc[0])
        capital_free = float(vypocitat_nevyuzity_kapital(last_date, df))
        portfolio_value_total = round(pv + capital_free, 2)

    invested_total = investovany_kapital(target_date, df)
    user = get_current_user()
    portfolio_id = (active_portfolio_data or {}).get("portfolio_id") if isinstance(active_portfolio_data, dict) else None
    if user and portfolio_id:
        active_portfolio = get_portfolio_for_user(user["id"], portfolio_id)
        if active_portfolio:
            source_portfolio_id = active_portfolio.get("source_portfolio_id")
            derived_from = active_portfolio.get("derived_from")
            baseline = active_portfolio.get("baseline_invested_capital")

            if derived_from and source_portfolio_id:
                source_df = load_portfolio_transactions_dataframe(user["id"], source_portfolio_id, fallback=df_empty)
                invested_total = calculate_net_invested_capital(source_df, target_date=target_date)
            elif baseline is not None:
                invested_total = float(baseline)

    total_profit = round((pv + capital_free) - invested_total, 2)
    roi = round(((total_profit / invested_total) * 100), 2) if invested_total else 0.0

    annualized_return = 0.0
    portfolio_volatility = 0.0
    max_drawdown = 0.0

    twr_df = twr_index_from_df(df, prices)
    if twr_df is not None and not twr_df.empty:
        twr_df = twr_df.copy()
        twr_df["date"] = _to_naive_day(twr_df["date"])
        twr_df = twr_df.dropna(subset=["date", "twr_index"]).sort_values("date").reset_index(drop=True)
        twr_df = twr_df[twr_df["date"] <= target_date]

        if not twr_df.empty:
            twr_returns = pd.to_numeric(twr_df["twr_return"], errors="coerce").dropna()
            if not twr_returns.empty:
                portfolio_volatility = float(twr_returns.std(ddof=1) * np.sqrt(252) * 100.0)

            twr_index = pd.to_numeric(twr_df["twr_index"], errors="coerce").dropna()
            if not twr_index.empty:
                running_max = twr_index.cummax()
                drawdowns = (twr_index / running_max) - 1.0
                max_drawdown = float(drawdowns.min() * 100.0)

                start_index = float(twr_index.iloc[0])
                end_index = float(twr_index.iloc[-1])
                start_date = pd.to_datetime(twr_df["date"].iloc[0])
                end_date = pd.to_datetime(twr_df["date"].iloc[-1])
                year_span = max((end_date - start_date).days / 365.25, 0.0)
                if start_index > 0 and end_index > 0 and year_span > 0:
                    annualized_return = float((((end_index / start_index) ** (1.0 / year_span)) - 1.0) * 100.0)

    return {
        "portfolio_value_total": round(portfolio_value_total, 2),
        "invested_total": round(float(invested_total), 2),
        "total_profit": round(total_profit, 2),
        "roi": round(roi, 2),
        "annualized_return": round(annualized_return, 2),
        "portfolio_volatility": round(portfolio_volatility, 2),
        "max_drawdown": round(max_drawdown, 2),
        "negative_theme": bool(pd.notna(total_profit) and total_profit < 0),
    }

def make_benchmark_series(
    twr_df, df_prices, tickers,
    date_col="date", ticker_col="Ticker_clean", price_col="adjusted_close",
    base=100.0
):
    if tickers is None: return {}
    if isinstance(tickers, str): tickers = [tickers]
    tickers = [t for t in tickers if t]

    px = df_prices.copy()
    px[date_col] = _to_naive_day(px[date_col])

    start = _to_naive_day(twr_df[date_col]).min()
    series = {}

    for t in tickers:
        sub = (px.loc[px[ticker_col] == t, [date_col, price_col]]
                 .dropna().sort_values(date_col))
        sub = sub[sub[date_col] >= start]
        if sub.empty: 
            continue
        base_price = pd.to_numeric(sub[price_col], errors="coerce").iloc[0]
        idx = base * (pd.to_numeric(sub[price_col], errors="coerce") / base_price)
        idx.index = sub[date_col].values 
        idx.name = t
        series[t] = idx
    return series

def _df_from_store(payload, fallback=None):
    """
    Převod payloadu ze Store -> DataFrame. Když je Store prázdný, vrať fallback.
    """
    if payload and isinstance(payload, dict) and payload.get("records"):
        return pd.DataFrame(payload["records"])
    return fallback

def _msg_figure(text="Vyber datum pro výpočet portfolia."):
    """
    Jednoduchý placeholder Figure s textem – hodí se, když Output je figure,
    ale chceme zobrazit zprávu místo grafu.
    """
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5,
                       showarrow=False, font=dict(size=16))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def _msg_figure(text="Vyber datum pro výpočet portfolia."):
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=16))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)")
    return fig


def _no_data_figure(title=None):
    fig = go.Figure()
    fig.add_annotation(
        text="ZADNA DATA",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=34, color="#00c896", family="Arial Black, Arial, sans-serif"),
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#111111",
        height=500,
        margin=dict(t=40, b=40, l=40, r=40),
        title=dict(
            text=title or "",
            y=1, x=0.5, xanchor='center', yanchor='top',
            font=dict(size=24, color='white', family='Arial')
        ),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig




# ---------------------------------------------------------------------------
# 1) Alokace aktiv v portfoliu
# ---------------------------------------------------------------------------
@app.callback(
    Output("vystup-div", "figure"),
    Input("vyber-datum", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data")
)
def spust_sjednoceni(vybrane_datum, language, active_portfolio_data):
    lang = normalize_language(language)
    if vybrane_datum is None:
        return _msg_figure(t(lang, "common.select_date_for_calc"))
    df = _get_current_portfolio_df(active_portfolio_data)
    if not _has_transaction_data(df):
        return _msg_figure(t(lang, "common.no_transactions"))

    try:
        
        target_date = _to_naive_ts(vybrane_datum)
        result_df = sjednoceni(target_date, df).sort_values("Total_value", ascending=False)
        colors = _green_black_palette(len(result_df))

        fig = go.Figure()
        total_value = float(result_df["Total_value"].sum()) if not result_df.empty else 0.0
        for idx, row in enumerate(result_df.itertuples(index=False)):
            pct = (float(row.Total_value) / total_value * 100.0) if total_value else 0.0
            fig.add_trace(
                go.Bar(
                    x=[row.Total_value],
                    y=[t(lang, "home.portfolio")],
                    orientation="h",
                    name=str(row.Ticker),
                    marker=dict(color=colors[idx], line=dict(color="rgba(255,255,255,0.14)", width=1)),
                    text=[f"{pct:.1f}%<br>{row.Total_value:.2f}"],
                    textposition="inside",
                    textfont=dict(color="white", size=13),
                    insidetextanchor="middle",
                    hovertemplate=f"{row.Ticker}: %{{x:.2f}}<extra></extra>",
                )
            )
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='#111111',
            height=500,
            margin=dict(t=40, b=40, l=40, r=40),
            title=dict(
                text=t(lang, "home.allocation_title"),
                y=1, x=0.5, xanchor='center', yanchor='top',
                font=dict(size=24, color='white', family='Arial')
            ),
            barmode="stack",
            bargap=0.22,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.18,
                xanchor="center",
                x=0.5,
                bgcolor="rgba(0,0,0,0.2)",
                font=dict(color="white"),
            ),
            xaxis=dict(
                visible=False,
                zeroline=False,
            ),
            yaxis=dict(
                title=None,
                tickfont=dict(color='white', family='Arial'),
                automargin=True,
            ),
        )
        return fig

    except Exception as e:
        return _msg_figure(t(lang, "common.error", error=str(e)))

# ---------------------------------------------------------------------------
# 2) Pasivní příjmy a výdaje
# ---------------------------------------------------------------------------
@app.callback(
    Output("vystup_fee_div", "figure"),
    Input("vyber-datum", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data")
)
def vypocitat_fees_divi(vybrane_datum, language, active_portfolio_data):
    lang = normalize_language(language)
    if vybrane_datum is None:
        return _msg_figure(t(lang, "common.select_date_for_calc"))
    df = _get_current_portfolio_df(active_portfolio_data)
    if not _has_transaction_data(df):
        return _msg_figure(t(lang, "common.no_transactions"))

    try:
        target_date = _to_naive_ts(vybrane_datum)
        result_df = fees_divi(target_date, df)
        if result_df.empty:
            return _no_data_figure(t(lang, "home.passive_income_title"))
        if pd.to_numeric(result_df["Total_money"], errors="coerce").fillna(0.0).abs().sum() == 0:
            return _no_data_figure(t(lang, "home.passive_income_title"))

        result_df = result_df.sort_values("Total_money", ascending=False)
        colors = _green_black_palette(len(result_df))

        fig = go.Figure()
        total_money = float(result_df["Total_money"].sum()) if not result_df.empty else 0.0
        for idx, row in enumerate(result_df.itertuples(index=False)):
            pct = (float(row.Total_money) / total_money * 100.0) if total_money else 0.0
            fig.add_trace(
                go.Bar(
                    x=[row.Total_money],
                    y=[t(lang, "home.cashflow")],
                    orientation="h",
                    name=str(row.Type),
                    marker=dict(color=colors[idx], line=dict(color="rgba(255,255,255,0.14)", width=1)),
                    text=[f"{pct:.1f}%<br>{row.Total_money:.2f}"],
                    textposition="inside",
                    textfont=dict(color="white", size=13),
                    insidetextanchor="middle",
                    hovertemplate=f"{row.Type}: %{{x:.2f}}<extra></extra>",
                )
            )
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='#111111',
            height=500,
            margin=dict(t=40, b=40, l=40, r=40),
            title=dict(
                text=t(lang, "home.passive_income_title"),
                y=1, x=0.5, xanchor='center', yanchor='top',
                font=dict(size=24, color='white', family='Arial')
            ),
            barmode="stack",
            bargap=0.22,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.18,
                xanchor="center",
                x=0.5,
                bgcolor="rgba(0,0,0,0.2)",
                font=dict(color="white"),
            ),
            xaxis=dict(
                visible=False,
                zeroline=False,
            ),
            yaxis=dict(
                title=None,
                tickfont=dict(color='white', family='Arial'),
                automargin=True,
            ),
        )
        return fig

    except Exception as e:
        return _msg_figure(t(lang, "common.error", error=str(e)))

# ---------------------------------------------------------------------------
# 3) Souhrnná tabulka portfolia
# ---------------------------------------------------------------------------
@app.callback(
    Output("vystup_tabulka_portfolio", "children"),
    Input("vyber-datum", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data")
)
def vypocitat_hlavni_tabulku(vybrane_datum, language, active_portfolio_data):
    lang = normalize_language(language)
    if vybrane_datum is None:
        return t(lang, "common.select_date_for_calc")
    df = _get_current_portfolio_df(active_portfolio_data)
    if not _has_transaction_data(df):
        return t(lang, "common.no_transactions")
    

    try:
        tickers = set(portfolio_tickers(df))
        prices = _get_portfolio_prices(df).query("Ticker_clean in @tickers")
        target_date = _to_naive_ts(vybrane_datum)
        result_df    = sjednoceni(target_date, df)
        result_price = soucasna_cena(target_date, prices)
        result_divi  = vypocet_dividend(target_date, df)

        result_df["Avg_purch_price"] = (result_df["Total_value"] / result_df["Total_quantity"]).round(2)
        result_df["Total_value"]     = result_df["Total_value"].round(2)
        result_df["Total_purch_val"] = result_df["Total_value"]
        result_df["Total_quantity"]  = result_df["Total_quantity"].round(2)
        result_df["Ticker_clean"] = result_df["Ticker"].astype(str).str.split(".").str[0]
        result_divi["Ticker_clean"] = result_divi["Ticker"].astype(str).str.split(".").str[0]

        final_df = pd.merge(result_df, result_price, on="Ticker_clean", how="left")
        final_df = pd.merge(
            final_df,
            result_divi[["Ticker_clean", "Total_money"]],
            on="Ticker_clean",
            how="left",
        )
        final_df["Total_curr_val"] = (final_df["Total_quantity"] * final_df["adjusted_close"]).round(2)
        final_df["Total_money"]    = final_df["Total_money"].fillna(0).round(2)
        final_df["Profit"]         = (final_df["Total_curr_val"] - final_df["Total_purch_val"] + final_df["Total_money"]).round(2)
        final_df["Dividenda"]      = final_df["Total_money"]

        final_df = final_df[[
            "Ticker", "Total_purch_val", "Total_curr_val",
            "Total_quantity", "Avg_purch_price", "Dividenda", "Profit"
        ]]
        final_df = final_df.rename(columns={
            "Ticker": "TICKER",
            "Total_purch_val": t(lang, "home.purchased_value"),
            "Total_curr_val": t(lang, "home.current_value"),
            "Total_quantity": t(lang, "home.total_quantity"),
            "Avg_purch_price": t(lang, "home.avg_purchase_price"),
            "Dividenda": t(lang, "home.dividend"),
            "Profit": t(lang, "home.profit"),
        })
        display_df = final_df.copy()
        currency_columns = [
            t(lang, "home.purchased_value"),
            t(lang, "home.current_value"),
            t(lang, "home.avg_purchase_price"),
            t(lang, "home.dividend"),
            t(lang, "home.profit"),
        ]
        for column in currency_columns:
            display_df[column] = display_df[column].apply(lambda value: _format_numeric_display(value, decimals=2, suffix="€"))
        display_df[t(lang, "home.total_quantity")] = display_df[t(lang, "home.total_quantity")].apply(
            lambda value: _format_numeric_display(value, decimals=4, trim_trailing=True)
        )

        return dash_table.DataTable(
            columns=[{"name": c, "id": c} for c in display_df.columns],
            data=display_df.to_dict("records"),
            style_table={"overflowX": "auto"},
            style_cell={
                "textAlign": "left",
                "backgroundColor": "#1e1e1e",
                "color": "white",
                "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
            },
            style_data_conditional=[
                {
                    "if": {"column_id": column},
                    "textAlign": "right",
                }
                for column in display_df.columns
                if column != "TICKER"
            ],
            style_header={
                "backgroundColor": "#2a2a2a",
                "color": "#fff",
                "fontWeight": "700",
                "borderBottom": "2px solid #00a17b",
                "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
                "fontSize": "18px",
                "padding": "12px 8px",
                "height": "40px"
            }
        )
    except Exception as e:
        return html.Pre(str(e))

# ---------------------------------------------------------------------------
# 4) Základní tabulka s metrikami (celková hodnota, ROI…)
# ---------------------------------------------------------------------------
@app.callback(
    Output("vystup_zaklad_tabulka", "children"),
    Input("vyber-datum", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data")
)
def vypocitat_celkovy_profit(vybrane_datum, language, active_portfolio_data):
    lang = normalize_language(language)
    if vybrane_datum is None:
        return t(lang, "common.select_date_for_calc")
    df = _get_current_portfolio_df(active_portfolio_data)
    if not _has_transaction_data(df):
        return t(lang, "common.no_transactions")

    try:
        target_date = _to_naive_ts(vybrane_datum)
        metrics = _resolve_summary_metrics(target_date, df, active_portfolio_data)
        str_roi = f"{metrics['roi']}%"

        vystup = pd.DataFrame({
            t(lang, "home.total_portfolio_value"): [_format_numeric_display(metrics["portfolio_value_total"], decimals=2, suffix="€")],
            t(lang, "home.total_invested"): [_format_numeric_display(metrics["invested_total"], decimals=2, suffix="€")],
            t(lang, "home.total_return"): [_format_numeric_display(metrics["total_profit"], decimals=2, suffix="€")],
            "ROI": [str_roi]
        })

        if not metrics["negative_theme"]:
            barva = "rgba(0, 161, 123, 0.48)"
        else:
            barva = "rgba(217, 74, 74, 0.42)"

        return dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in vystup.columns],
            data=vystup.to_dict("records"),
            style_table={
                "overflowX": "auto",
                "margin": "auto",
                "marginTop": "20px",
                "marginBottom": "20px",
                "border": "2px solid white",
                "borderRadius": "10px",
                "backgroundColor": "#1e1e1e",
            },
            style_cell={
                "textAlign": "center",
                "backgroundColor": barva,
                "color": "white",
                "fontSize": "24px",
                "fontWeight": "bold",
                "padding": "20px",
                "width": f"{100 / max(len(vystup.columns), 1)}%",
                "minWidth": f"{100 / max(len(vystup.columns), 1)}%",
                "maxWidth": f"{100 / max(len(vystup.columns), 1)}%",
            },
            style_header={
                "fontSize": "20px",
                "fontWeight": "bold",
                "textAlign": "center",
                "backgroundColor": "#333333",
                "color": "white",
            },
        )

    except Exception as e:
        return html.Pre(str(e))

# ---------------------------------------------------------------------------
# 5) Portfolio KPI block
# ---------------------------------------------------------------------------
@app.callback(
    Output("portfolio-risk-summary", "children"),
    Input("vyber-datum", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data")
)
def vypocitat_portfolio_risk_summary(vybrane_datum, language, active_portfolio_data):
    lang = normalize_language(language)
    if vybrane_datum is None:
        return t(lang, "common.select_date_for_calc")
    df = _get_current_portfolio_df(active_portfolio_data)
    if not _has_transaction_data(df):
        return t(lang, "common.no_transactions")
    try:
        target_date = _to_naive_ts(vybrane_datum)
        metrics = _resolve_summary_metrics(target_date, df, active_portfolio_data)
        barva = "rgba(217, 74, 74, 0.42)" if metrics["negative_theme"] else "rgba(0, 161, 123, 0.48)"
        risk_df = pd.DataFrame({
            t(lang, "home.annualized_return"): [f"{metrics['annualized_return']}%"],
            t(lang, "home.max_drawdown"): [f"{metrics['max_drawdown']}%"],
            t(lang, "home.portfolio_volatility"): [f"{metrics['portfolio_volatility']}%"],
        })

        return dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in risk_df.columns],
            data=risk_df.to_dict("records"),
            style_table={
                "overflowX": "auto",
                "margin": "auto",
                "marginTop": "20px",
                "marginBottom": "20px",
                "border": "2px solid white",
                "borderRadius": "10px",
                "backgroundColor": "#1e1e1e",
            },
            style_cell={
                "textAlign": "center",
                "backgroundColor": barva,
                "color": "white",
                "fontSize": "24px",
                "fontWeight": "bold",
                "padding": "20px",
                "width": f"{100 / max(len(risk_df.columns), 1)}%",
                "minWidth": f"{100 / max(len(risk_df.columns), 1)}%",
                "maxWidth": f"{100 / max(len(risk_df.columns), 1)}%",
            },
            style_header={
                "fontSize": "20px",
                "fontWeight": "bold",
                "textAlign": "center",
                "backgroundColor": "#333333",
                "color": "white",
            },
        )
    except Exception as e:
        return html.Pre(str(e))

# ---------------------------------------------------------------------------
# 6) Ukazatele rizika – tabulka
# ---------------------------------------------------------------------------
@app.callback(
    Output("asset-risk-summary", "children"),
    Input("vyber-datum", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data")
)
def vypocitat_asset_risk_summary(vybrane_datum, language, active_portfolio_data):
    lang = normalize_language(language)
    if vybrane_datum is None:
        return t(lang, "common.select_date_for_calc")
    df = _get_current_portfolio_df(active_portfolio_data)
    if not _has_transaction_data(df):
        return t(lang, "common.no_transactions")
    tickers = set(portfolio_tickers(df))
    prices = _get_portfolio_prices(df).query("Ticker_clean in @tickers")
    target_date = _force_naive_scalar(vybrane_datum)
    dfp = prices.sort_values(["Ticker_clean", "date"]).copy()
    dfp["date"] = _to_naive_day(dfp["date"])
    dfp = dfp.query("date <= @target_date")
    dfp["Return"] = dfp.groupby("Ticker_clean")["adjusted_close"].pct_change()

    risk_free_rate = 0.042
    risk_rows = []

    for ticker, group in dfp.groupby("Ticker_clean"):
        returns = group["Return"].dropna()
        if returns.empty:
            continue

        mean_return = returns.mean()
        std_return = returns.std()
        annual_return = mean_return * 252
        annual_volatility = std_return * np.sqrt(252)
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0.0

        downside_returns = returns[returns < (risk_free_rate / 252)]
        downside_deviation = downside_returns.std()
        annual_downside_deviation = downside_deviation * np.sqrt(252)
        sortino_ratio = (annual_return - risk_free_rate) / annual_downside_deviation if annual_downside_deviation != 0 else 0.0

        risk_rows.append({
            "Ticker": ticker,
            t(lang, "home.volatility"): round(std_return, 6),
            "Sharpe Ratio": round(sharpe_ratio, 6),
            "Sortino Ratio": round(sortino_ratio, 6),
        })

    risk_df = pd.DataFrame(risk_rows).sort_values(by="Ticker") if risk_rows else pd.DataFrame(
        columns=["Ticker", t(lang, "home.volatility"), "Sharpe Ratio", "Sortino Ratio"]
    )
    display_risk_df = risk_df.copy()
    for column in [t(lang, "home.volatility"), "Sharpe Ratio", "Sortino Ratio"]:
        if column in display_risk_df.columns:
            display_risk_df[column] = display_risk_df[column].apply(
                lambda value: _format_numeric_display(value, decimals=6, trim_trailing=True)
            )

    return dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in display_risk_df.columns],
        data=display_risk_df.to_dict("records"),
        style_table={"overflowX": "auto"},
        style_cell={
            "textAlign": "left",
            "backgroundColor": "#1e1e1e",
            "color": "white",
            "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
        },
        style_data_conditional=[
            {
                "if": {"column_id": column},
                "textAlign": "right",
            }
            for column in display_risk_df.columns
            if column != "Ticker"
        ],
        style_header={
            "backgroundColor": "#2a2a2a",
            "color": "#fff",
            "fontWeight": "700",
            "borderBottom": "2px solid #00a17b",
            "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
            "fontSize": "18px",
            "padding": "12px 8px",
            "height": "40px"
        }
    )

# ---------------------------------------------------------------------------
# 7) Graf vývoje ceny vybraných aktiv
# ---------------------------------------------------------------------------
@app.callback(
    Output("price-graph", "figure"),
    Input("ticker-dropdown", "value"),
    Input("vyber-start_date", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data")
)
def single_performance_graph(selected_tickers, selected_start_date, language, active_portfolio_data):
    lang = normalize_language(language)
    if not selected_tickers:
        return _msg_figure(t(lang, "common.choose_assets"))
    df = _get_current_portfolio_df(active_portfolio_data)
    if not _has_transaction_data(df):
        return _msg_figure(t(lang, "common.no_transactions"))
    tickers = set(portfolio_tickers(df))
    prices = _get_portfolio_prices(df).query("Ticker_clean in @tickers")
    if selected_start_date is None:
        target_date = _to_naive_day(prices["date"]).max()
    else:
        target_date = _force_naive_scalar(selected_start_date)

    filtered_data = prices.query("Ticker_clean in @selected_tickers").copy()
    filtered_data["date"] = _to_naive_day(filtered_data["date"])
    normalized_df = filtered_data.sort_values(["Ticker_clean", "date"])
    normalized_df = normalized_df[normalized_df["date"] >= target_date]
    first_prices = normalized_df.groupby("Ticker_clean")["adjusted_close"].transform("first")

    normalized_df["normalized_price"] = (normalized_df["adjusted_close"] / first_prices) * 100

    fig = px.line(
        normalized_df,
        x="date", y="normalized_price", color="Ticker_clean",
        labels={"normalized_price": t(lang, "home.indexed_price"), "Ticker_clean": "Ticker"},
        title=t(lang, "home.relative_prices"),
        color_discrete_sequence=_green_black_palette(max(len(normalized_df["Ticker_clean"].unique()), 1)),
    )
    fig.update_layout(
        showlegend=True,
        legend=dict(
            title=t(lang, "home.assets_legend"),
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(0, 0, 0, 0.2)",
            font=dict(color='white'),
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#303030',
        height=500,
        margin=dict(t=40, b=40, l=40, r=40),
        title=dict(text=t(lang, "home.relative_prices"),
                   y=1, x=0.5, xanchor='center', yanchor='top',
                   font=dict(size=24, color='white', family='Arial')),
        xaxis=dict(title=dict(text=t(lang, "home.date"), font=dict(size=18, color='white', family='Arial')),
                   tickfont=dict(color='white', family='Arial'),
                   showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1),
        yaxis=dict(title=dict(text=t(lang, "home.indexed_price"), font=dict(size=18, color='white', family='Arial')),
                   tickfont=dict(color='white', family='Arial'),
                   showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1),
        shapes=[dict(type="line", xref="paper", x0=0, x1=1, yref="y", y0=100, y1=100,
                     line=dict(color="white", width=1, dash="dot"))],
    )
    return fig


@app.callback(
    Output("ticker-dropdown", "options"),
    Output("ticker-dropdown", "value"),
    Input("vyber-datum", "date"),
    State("active-portfolio-store", "data"),
)
def update_home_ticker_dropdown(_selected_date, active_portfolio_data):
    df_local = _get_current_portfolio_df(active_portfolio_data)
    tickers_local = sorted(portfolio_tickers(df_local))
    options = [{"label": ticker, "value": ticker} for ticker in tickers_local]
    return options, tickers_local

# ---------------------------------------------------------------------------
# 8) Porovnání s benchmarky
# ---------------------------------------------------------------------------
@app.callback(
    Output("compare_graph", "figure"),
    Input("compare_tickers", "value"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data"),
)
def compare_graph(selected_bench, language, active_portfolio_data):
    lang = normalize_language(language)
    df_local = _get_current_portfolio_df(active_portfolio_data)

    if not _has_transaction_data(df_local):
        return _msg_figure(t(lang, "common.no_transactions"))

    tickers_clean = (
        df_local["Ticker"].astype(str).str.split(".").str[0].dropna().unique().tolist()
        if not df_local.empty else []
    )
    prices_filtered = _get_portfolio_prices(df_local)
    prices_filtered = prices_filtered[prices_filtered["Ticker_clean"].isin(tickers_clean)].copy()

    twr_df = twr_index_from_df(df_local, prices_filtered, base=100.0)

    default_benchmarks = ["SXR8"]
    if not selected_bench:
        bench_tickers = default_benchmarks
    else:
        if isinstance(selected_bench, str):
            selected_bench = [selected_bench]
        bench_tickers = sorted(set(selected_bench).union(default_benchmarks))

    benchmark_prices = load_market_data(tickers=bench_tickers, use_cache=False)

    bench = make_benchmark_series(
        twr_df, benchmark_prices, bench_tickers,
        date_col="date", ticker_col="Ticker_clean",
        price_col="adjusted_close", base=100.0
    )

    fig = go.Figure()
    series_colors = _green_black_palette(max(len(bench) + 1, 1))
    fig.add_trace(go.Scatter(
        x=twr_df["date"], y=twr_df["twr_index"],
        mode="lines", name=f"{t(lang, 'home.portfolio')} (TWR = 100)",
        line=dict(color=series_colors[0], width=2), connectgaps=False
    ))

    for idx, (name, s) in enumerate(bench.items(), start=1):
        s = s.reindex(twr_df["date"].values)
        fig.add_trace(go.Scatter(
            x=twr_df["date"], y=s.values, mode="lines", name=f"{name} (=100)",
            line=dict(color=series_colors[idx % len(series_colors)], width=2),
            connectgaps=False
        ))

    fig.update_layout(
        autosize=True, height=500,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#303030",
        margin=dict(t=40, b=40, l=40, r=40),
        title=dict(text=t(lang, "home.normalized_compare"),
                   y=1, x=0.5, xanchor="center", yanchor="top",
                   font=dict(size=24, color="white", family="Arial")),
        xaxis=dict(title=dict(text=t(lang, "home.date"), font=dict(size=18, color="white", family="Arial")),
                   tickfont=dict(color="white", family="Arial"),
                   showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1),
        yaxis=dict(title=dict(text=t(lang, "home.index_base_100"), font=dict(size=18, color="white", family="Arial")),
                   tickfont=dict(color="white", family="Arial"),
                   showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1),
        showlegend=True,
        legend=dict(
            title=t(lang, "home.assets_legend"),
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(0, 0, 0, 0.2)",
            font=dict(color='white'),
        ),
        shapes=[dict(type="line", xref="paper", x0=0, x1=1, yref="y", y0=100, y1=100,
                     line=dict(color="white", width=1, dash="dot"))]
    )
    return fig


# ---------------------------------------------------------------------------
# 9) Hodnota portfolia v čase (Daily/Monthly)
# ---------------------------------------------------------------------------
@app.callback(
    Output("portfolio_v_case", "children"),
    Input("frequency-dropdown", "value"),
    Input("vyber-datum", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data")
)
def graf_portfolio_v_case(freq, vybrane_datum, language, active_portfolio_data):
    lang = normalize_language(language)
    if vybrane_datum is None:
        return t(lang, "common.select_date_for_calc")
    df = _get_current_portfolio_df(active_portfolio_data)
    if not _has_transaction_data(df):
        return t(lang, "common.no_transactions")

    try:
        tickers = set(portfolio_tickers(df))
        prices = _get_portfolio_prices(df).query("Ticker_clean in @tickers")
        target_date = _force_naive_scalar(vybrane_datum)
        result_df = hodnota_portfolia_v_case(target_date, df, prices)

        plot_df = result_df.copy()
        plot_df = plot_df.sort_values("date")
        plot_df = plot_df.dropna(subset=["portfolio_value"])
        plot_df = plot_df[plot_df["portfolio_value"] > 0]

        if freq == "Monthly":
            plot_df["date"] = pd.to_datetime(plot_df["date"])
            plot_df["year_month"] = plot_df["date"].dt.to_period("M")
            plot_df = plot_df.sort_values("date").groupby("year_month").tail(1)
            plot_df = plot_df.drop(columns="year_month")

        plot_df["prev"] = plot_df["portfolio_value"].shift(1)
        plot_df["next"] = plot_df["portfolio_value"].shift(-1)
        plot_df = plot_df[(plot_df["prev"].notna()) | (plot_df["next"].notna())]

        if plot_df.empty:
            return t(lang, "home.no_valid_data")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df["date"],
            y=plot_df["portfolio_value"],
            mode="lines",
            name=t(lang, "home.portfolio"),
            line=dict(color="#00c896", width=2),
            fill="tozeroy",
            fillcolor="rgba(0, 161, 123, 0.24)",
            connectgaps=False
        ))

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='#303030',
            height=500,
            margin=dict(t=40, b=40, l=40, r=40),
            title=dict(
                text=t(lang, "home.portfolio_value_history"),
                y=1, x=0.5, xanchor='center', yanchor='top',
                font=dict(size=24, color='white', family='Arial')
            ),
            xaxis=dict(
                title=dict(text=t(lang, "home.date"), font=dict(size=18, color='white', family='Arial')),
                tickfont=dict(color='white', family='Arial'),
                showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1
            ),
            yaxis=dict(
                title=dict(text=t(lang, "home.value_eur"), font=dict(size=18, color='white', family='Arial')),
                tickfont=dict(color='white', family='Arial'),
                showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1
            ),
            showlegend=False
        )

        return dcc.Graph(figure=fig)

    except Exception as e:
        return html.Pre(str(e))



# ---------------------------------------------------------------------------
# Callback na upload nových csv
# ---------------------------------------------------------------------------
@app.callback(
    Output("monthly-dividends-graph", "figure"),
    Input("vyber-datum", "date"),
    Input("language-store", "data"),
    State("active-portfolio-store", "data"),
)
def monthly_dividends_graph(_selected_date, language, active_portfolio_data):
    lang = normalize_language(language)
    def _placeholder(msg):
        fig = go.Figure()
        fig.add_annotation(
            text=msg,
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color="white"),
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#303030",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        return fig

    df_local = _get_current_portfolio_df(active_portfolio_data)

    required = {"Type", "Date", "Total Amount"}
    if df_local.empty or not required.issubset(set(df_local.columns)):
        return _placeholder(t(lang, "home.monthly_dividend_missing_data"))

    all_dates = pd.to_datetime(df_local["Date"], errors="coerce", utc=True).dt.tz_convert(None).dropna()
    if all_dates.empty:
        return _placeholder(t(lang, "home.monthly_dividend_missing_dates"))

    month_start = all_dates.min().to_period("M").to_timestamp()
    month_end = all_dates.max().to_period("M").to_timestamp()
    full_months = pd.DataFrame({"month": pd.date_range(month_start, month_end, freq="MS")})

    div = df_local[df_local["Type"].astype(str).str.contains("DIVIDEND", na=False)].copy()
    if div.empty:
        return _no_data_figure(t(lang, "home.monthly_dividend_income"))
    else:
        div["Date"] = pd.to_datetime(div["Date"], errors="coerce", utc=True).dt.tz_convert(None)
        div["Total_clean"] = _parse_money_series(div["Total Amount"])
        div = div.dropna(subset=["Date", "Total_clean"])
        if div.empty:
            return _no_data_figure(t(lang, "home.monthly_dividend_income"))
        else:
            div["month"] = div["Date"].dt.to_period("M").dt.to_timestamp()
            monthly = div.groupby("month", as_index=False)["Total_clean"].sum().sort_values("month")
            monthly = full_months.merge(monthly, on="month", how="left").fillna({"Total_clean": 0.0})

    if monthly["Total_clean"].abs().sum() == 0:
        return _no_data_figure(t(lang, "home.monthly_dividend_income"))

    fig = go.Figure(
        data=[
            go.Bar(
                x=monthly["month"],
                y=monthly["Total_clean"],
                marker_color="#008f6b",
                marker_line_color="#00c896",
                marker_line_width=1,
                width=1000 * 60 * 60 * 24 * 20,  # fixed ~20-day width to avoid edge stretching
                name=t(lang, "home.dividend"),
            )
        ]
    )
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#303030',
        height=500,
        margin=dict(t=40, b=40, l=40, r=40),
        title=dict(
            text=t(lang, "home.monthly_dividend_income"),
            y=1, x=0.5, xanchor='center', yanchor='top',
            font=dict(size=24, color='white', family='Arial')
        ),
        xaxis=dict(
            title=dict(text=t(lang, "home.month"), font=dict(size=18, color='white', family='Arial')),
            tickfont=dict(color='white', family='Arial'),
            showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1,
            type="date",
            dtick="M1",
            tickformat="%Y-%m",
        ),
        yaxis=dict(
            title=dict(text=t(lang, "home.amount"), font=dict(size=18, color='white', family='Arial')),
            tickfont=dict(color='white', family='Arial'),
            showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1,
            rangemode="tozero",
        ),
        showlegend=False,
        bargap=0.2,
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=monthly["month"],
        ticktext=monthly["month"].dt.strftime("%Y-%m"),
        range=[
            monthly["month"].min() - pd.Timedelta(days=15),
            monthly["month"].max() + pd.Timedelta(days=15),
        ],
    )
    return fig


@app.callback(
    Output("dashboard-empty-overlay", "style"),
    Input("url", "pathname"),
    Input("active-portfolio-store", "data"),
)
def toggle_home_empty_state(pathname, active_portfolio_data):
    waiting = pathname == "/dashboard" and _show_waiting_state(active_portfolio_data)
    if not waiting:
        return {"display": "none"}
    return {
        "display": "flex",
        "position": "fixed",
        "top": "88px",
        "left": "0",
        "right": "0",
        "bottom": "0",
        "width": "100%",
        "minHeight": "calc(100vh - 88px)",
        "zIndex": "900",
        "background": "linear-gradient(to bottom right, #0e0e0e, #0e0e0e, #0e0e0e, #0e0e0e, #0e0e0e, #0e0e0e, #0e0e0e, #0e0e0e, #00281f, #015140, #00a17b)",
        "alignItems": "center",
        "justifyContent": "center",
        "padding": "24px",
        "boxSizing": "border-box",
    }


@app.callback(
    Output("portfolio-list-store", "data", allow_duplicate=True),
    Output("active-portfolio-store", "data", allow_duplicate=True),
    Output("upload-status", "children"),
    Input("upload-data", "contents"),
    State("upload-data", "filename"),
    State("active-portfolio-store", "data"),
    State("language-store", "data"),
    prevent_initial_call=True,
)
def upload_and_store(contents, filename, active_portfolio_data, language):
    lang = normalize_language(language)
    if contents is None:
        return dash.no_update, dash.no_update, dash.no_update

    user = get_current_user()
    portfolio_id = (active_portfolio_data or {}).get("portfolio_id") if isinstance(active_portfolio_data, dict) else None
    if not user or not portfolio_id:
        return dash.no_update, dash.no_update, t(lang, "common.no_active_portfolio")

    try:
        df_uploaded = parse_upload_contents(contents, filename=filename)
        market_data_summary = ensure_market_data_for_portfolio_dataframe(df_uploaded)
        import_transactions_dataframe(
            portfolio_id=portfolio_id,
            dataframe=df_uploaded,
            filename=filename,
            market_data_summary=market_data_summary,
        )
        portfolios = list_user_portfolios(user["id"])
        status_parts = [t(lang, "home.upload_success", rows=len(df_uploaded))]
        downloaded = market_data_summary.get("downloaded_tickers") or []
        if downloaded:
            status_parts.append(t(lang, "home.market_data_downloaded", tickers=", ".join(downloaded)))
        overlap_start = market_data_summary.get("overlap_start")
        overlap_end = market_data_summary.get("overlap_end")
        if overlap_start and overlap_end:
            status_parts.append(t(lang, "home.price_overlap", start=overlap_start, end=overlap_end))
        import_warnings = df_uploaded.attrs.get("import_warnings") or []
        if import_warnings:
            status_parts.append(t(lang, "home.autocorrections", warnings=" ".join(import_warnings)))
        return (
            portfolios,
            {"portfolio_id": portfolio_id},
            " ".join(status_parts),
        )
    except Exception as exc:
        return dash.no_update, dash.no_update, t(lang, "home.upload_failed", error=str(exc))


@app.callback(
    Output({"type": "dashboard-section-content", "index": MATCH}, "className"),
    Output({"type": "dashboard-section-arrow", "index": MATCH}, "children"),
    Input({"type": "dashboard-section-toggle", "index": MATCH}, "n_clicks"),
    prevent_initial_call=False,
)
def toggle_dashboard_section(n_clicks):
    is_open = bool(n_clicks and n_clicks % 2 == 1)
    return (
        "dashboard-section-content is-open" if is_open else "dashboard-section-content",
        "▴" if is_open else "▾",
    )
 

@app.callback(
    Output("home-hero-title", "children"),
    Output("home-hero-subtitle", "children"),
    Output("dashboard-section-title-portfolio-table", "children"),
    Output("dashboard-section-title-asset-risk-table", "children"),
    Output("dashboard-section-title-portfolio-value-history", "children"),
    Output("dashboard-section-title-asset-selection", "children"),
    Output("dashboard-section-title-benchmark-compare", "children"),
    Output("dashboard-section-title-portfolio-breakdown", "children"),
    Output("dashboard-section-title-monthly-dividends", "children"),
    Output("home-frequency-label", "children"),
    Output("frequency-dropdown", "options"),
    Output("home-assets-label", "children"),
    Output("home-start-date-label", "children"),
    Output("vyber-start_date", "placeholder"),
    Output("home-compare-label", "children"),
    Input("language-store", "data"),
)
def localize_home_static_text(language):
    lang = normalize_language(language)
    return (
        t(lang, "home.title"),
        t(lang, "home.subtitle"),
        t(lang, "home.section.portfolio_table"),
        t(lang, "home.section.asset_risk"),
        t(lang, "home.section.value_history"),
        t(lang, "home.section.asset_selection"),
        t(lang, "home.section.benchmark_compare"),
        t(lang, "home.section.breakdown"),
        t(lang, "home.section.monthly_dividends"),
        t(lang, "home.frequency_label"),
        _home_frequency_options(lang),
        t(lang, "home.assets_label"),
        t(lang, "home.start_date_label"),
        t(lang, "sidebar.select_date"),
        t(lang, "home.compare_label"),
    )


layout = html.Div(
    className="home-page",
    children=[
        html.Div(
            children=[
                # Nadpis
                html.Div(
                    className="hero",
                    children=[
                        html.H1("Analýza portfolia", id="home-hero-title", className="nadpis"),
                        html.P("Školní projekt - testovací verze", id="home-hero-subtitle", className="podnadpis"),
                    ],
                ),

                # Hlavní část
                html.Div(
                    className="content",
                    children=[
                        html.Div(
                            className="left-col",
                            children=[
                                html.Div(id="vystup_zaklad_tabulka"),
                                html.Div(id="portfolio-risk-summary"),
                                _build_dashboard_section(
                                    "portfolio-table",
                                    "Souhrnna tabulka portfolia",
                                    html.Div(
                                        className="dropdown-graph-wrapper",
                                        children=[
                                            html.Div(id="vystup_tabulka_portfolio"),
                                        ],
                                    ),
                                ),
                                _build_dashboard_section(
                                    "asset-risk-table",
                                    "Ukazatele rizika",
                                    html.Div(
                                        className="dropdown-graph-wrapper",
                                        children=[
                                            html.Div(id="asset-risk-summary", className="modern-table"),
                                        ],
                                    ),
                                ),
                                _build_dashboard_section(
                                    "portfolio-value-history",
                                    "Hodnota portfolia v case",
                                    html.Div(
                                        className="dropdown-graph-wrapper",
                                        children=[
                                            html.H2("Vyber frekvenci dat:", id="home-frequency-label"),
                                            dcc.Dropdown(
                                                _home_frequency_options("cs"),
                                                'Daily',
                                                id='frequency-dropdown',
                                                className="dropdown"
                                            ),
                                            html.Div(id="portfolio_v_case"),
                                        ],
                                    ),
                                ),
                                _build_dashboard_section(
                                    "asset-selection",
                                    "Vyber aktiva",
                                    html.Div(
                                        className="dropdown-graph-wrapper",
                                        children=[
                                            html.H2("Vyber aktiva:", id="home-assets-label"),
                                            dcc.Dropdown(
                                                tickers_l,
                                                tickers_l_default,
                                                id='ticker-dropdown',
                                                multi=True,
                                                className="dropdown"
                                            ),
                                            html.H2("Vyber pocatecni datum:", id="home-start-date-label"),
                                            dcc.DatePickerSingle(
                                                id="vyber-start_date",
                                                date=min(df_prices["date"]),
                                                display_format="DD.MM.YYYY",
                                                placeholder="Vyber datum",
                                            ),
                                            dcc.Graph(id="price-graph", className="graph"),
                                        ],
                                    ),
                                ),
                                _build_dashboard_section(
                                    "benchmark-compare",
                                    "Porovnani s benchmarky",
                                    html.Div(
                                        className="dropdown-graph-wrapper",
                                        children=[
                                            html.H2("Vyber aktiva na porovnani:", id="home-compare-label"),
                                            dcc.Dropdown(
                                                tickers_all,
                                                tickers_default,
                                                id='compare_tickers',
                                                multi=True,
                                                className="dropdown"
                                            ),
                                            dcc.Graph(id="compare_graph", className="graph"),
                                        ],
                                    ),
                                ),
                                _build_dashboard_section(
                                    "portfolio-breakdown",
                                    "Slozeni portfolia a poplatky",
                                    html.Div(
                                        className="dropdown-graph-wrapper",
                                        children=[
                                            html.Div(
                                                className="row-container",
                                                children=[
                                                    dcc.Graph(id="vystup-div", className="mini-graph"),
                                                    dcc.Graph(id="vystup_fee_div", className="mini-graph"),
                                                ],
                                            )
                                        ],
                                    ),
                                ),
                                _build_dashboard_section(
                                    "monthly-dividends",
                                    "Dividendy po mesicich",
                                    html.Div(
                                        className="dropdown-graph-wrapper",
                                        children=[
                                            dcc.Graph(id="monthly-dividends-graph", className="graph"),
                                        ],
                                    ),
                                ),
                            ],
                        ),
                        html.Div(id="home-upload-status-note", style={"display": "none"}),
                    ],
                ),
            ],
        )
    ],
)


