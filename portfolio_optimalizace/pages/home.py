from dash import register_page, html, dcc, dash_table, no_update
from dash import Input, Output, callback, State
import pandas as pd
import plotly.express as px
from datetime import date
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import io, base64
from threading import Lock
import dash

register_page(__name__, path="/")
#--------------- Načítání dat i s fallbackem (Později změnit na prázdný fallback!)
df_fallback = pd.read_csv("portfolio.csv", sep=None, engine="python")
df = df_fallback.copy()
df_default = df.copy()
tickers = set(df["Ticker"])
df_prices = pd.read_csv("df_prices.csv")
df_prices_all = pd.read_csv("df_prices.csv")
df_prices["Ticker_clean"] = df_prices["Ticker"].str.split(".").str[0]
df_prices_all = df_prices.copy()
tickers_all = list(set(df_prices["Ticker_clean"]))
tickers_default = ['SXR8']
df_prices = df_prices.query("Ticker_clean in @tickers")
tickers_l = list(set(df_prices["Ticker_clean"]))
tickers_l_default = tickers_l
snp500 = df_prices.query("Ticker_clean == 'SXR8'")
#---------------



def _to_naive_ts(x):
    """Scalar → tz-naive pd.Timestamp normalizovaný na půlnoc."""
    ts = pd.to_datetime(x, utc=True)
    return ts.tz_convert(None).normalize()
def _to_naive_day(s):
    s = pd.to_datetime(s, errors="coerce", utc=True)
    s = s.dt.tz_convert(None)
    return s.dt.floor("D")

def _to_naive_series(s):
    """Series → tz-naive datetime64[ns] normalizovaný na půlnoc."""
    s = pd.to_datetime(s, errors="coerce", utc=True)
    return s.dt.tz_convert(None).dt.normalize()

def _force_naive_series(s):
    s = pd.to_datetime(s, errors="coerce", utc=True)
    s = s.dt.tz_convert(None)       
    return s.dt.normalize()

def _force_naive_scalar(ts):
    ts = pd.to_datetime(ts, utc=True) 
    ts = ts.tz_convert(None)      
    return ts.normalize()

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

    df_copy = data.copy()
    df_copy["Date"] = pd.to_datetime(df_copy["Date"], utc=True).dt.normalize()
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
    target_date = pd.to_datetime(target_date, utc=True).normalize()
    df_copy = df_prices.copy()
    df_copy["date"] = pd.to_datetime(df_copy["date"], utc=True).dt.normalize()
    max_date = df_copy.loc[df_copy["date"] <= target_date, "date"].max()
    df_copy = df_copy[df_copy["date"] == max_date]
    return df_copy[["Ticker_clean", "adjusted_close"]]

def celkove_fee_divi(target_date, data):
    target_date = pd.to_datetime(target_date, utc=True).normalize()

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True).dt.normalize()
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
    df_copy = data.copy()
    df_copy["Date"] = pd.to_datetime(df_copy["Date"], utc=True).dt.normalize()
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
    df = df.sort_values(by="Date")

    df = df[df["Type"].isin(["BUY - MARKET", "SELL - MARKET"])]

    df_copy = df.copy()
    df_copy["Total_clean"] = (
        df_copy["Total Amount"]
        .astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df_copy["Total_quant_clean"] = np.where(
        df_copy["Type"] == "SELL - MARKET",
        -df_copy["Quantity"],
        df_copy["Quantity"]
    )
    df_copy["Total_clean"] = df_copy["Total_clean"].astype(float)
    df_copy["Total_clean"] = np.where(
        df_copy["Type"] == "SELL - MARKET",
        -df_copy["Total_clean"],
        df_copy["Total_clean"]
    )

    df_copy["CumulativeShares"] = df_copy.groupby("Ticker")["Total_quant_clean"].cumsum()
    df_copy = df_copy[["Date", "Ticker", "CumulativeShares"]]

    df_copy["Date"] = pd.to_datetime(df_copy["Date"]).dt.tz_localize(None).dt.normalize()
    df_prices["date"] = pd.to_datetime(df_prices["date"]).dt.tz_localize(None).dt.normalize()
    min_date = df_copy["Date"].min()
    df_prices = df_prices[df_prices["date"] >= min_date]

    final = pd.merge(
        df_prices,
        df_copy,
        left_on=["date", "Ticker_clean"],
        right_on=["Date", "Ticker"],
        how="left"
    )

    final = final.sort_values(by=["Ticker_clean", "date"])
    final["CumulativeShares"] = final.groupby("Ticker_clean")["CumulativeShares"].ffill()
    final["position_value"] = final["CumulativeShares"] * final["adjusted_close"]
    final["portfolio_value"] = final.groupby("date")["position_value"].transform("sum")
    first_valid_date = final[final["portfolio_value"] > 0]["date"].min()
    final = final[final["date"] >= first_valid_date]

    return final
def vypocitat_nevyuzity_kapital(target_date, df):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_convert(None)
    df = df[df["Date"] <= target_date]
    df["Total_clean"] = (
        df["Total Amount"]
        .astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
        .astype(float)
    )
    volny_kapital = 0.0
    for _, row in df.iterrows():
        typ = row["Type"]
        castka = row["Total_clean"]
        if typ == "CASH TOP-UP":
            volny_kapital += castka
        elif typ in ["BUY - MARKET"]:
            volny_kapital -= castka
        elif typ in ["DIVIDEND", "SELL - MARKET", "ROBO MANAGEMENT FEE", "CASH WITHDRAWAL"]:
            volny_kapital += castka

    return round(volny_kapital, 2)

def hodnota_portfolia_v_case_tabulka(target_date, df, df_prices):
    def _s_to_naive(s):
        s = pd.to_datetime(s, errors="coerce", utc=True)
        return s.dt.tz_convert(None).dt.normalize()
    def _ts_to_naive(ts):
        ts = pd.to_datetime(ts, errors="coerce", utc=True)
        return ts.tz_convert(None).normalize() if pd.notna(ts) else pd.NaT

    td = _ts_to_naive(target_date)

    base = df[df["Type"].isin(["BUY - MARKET", "SELL - MARKET"])].copy()
    if base.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])

    base["Date"] = _s_to_naive(base["Date"])
    dfp = df_prices.copy()
    dfp["date"] = _s_to_naive(dfp["date"])

    base["Quantity"] = pd.to_numeric(base["Quantity"], errors="coerce").fillna(0.0)
    base["Total_quant_clean"] = np.where(base["Type"].eq("SELL - MARKET"),
                                         -base["Quantity"], base["Quantity"])

    base = base.sort_values(["Ticker", "Date"])
    base["CumulativeShares"] = base.groupby("Ticker", sort=False)["Total_quant_clean"].cumsum()
    base = base[["Date", "Ticker", "CumulativeShares"]]

    min_date = base["Date"].min()
    if pd.isna(min_date):
        return pd.DataFrame(columns=["date", "portfolio_value"])
    dfp = dfp[dfp["date"] >= min_date].drop_duplicates(subset=["date","Ticker_clean"])

    final = pd.merge(
        dfp, base,
        left_on=["date","Ticker_clean"],
        right_on=["Date","Ticker"],
        how="left",
    ).sort_values(["Ticker_clean","date"])
    final["CumulativeShares"] = final.groupby("Ticker_clean", sort=False)["CumulativeShares"].ffill().fillna(0.0)
    final["adjusted_close"] = pd.to_numeric(final["adjusted_close"], errors="coerce").fillna(0.0)

    final["position_value"] = final["CumulativeShares"] * final["adjusted_close"]

    by_day = (final.groupby("date", as_index=False)["position_value"]
                    .sum()
                    .rename(columns={"position_value":"portfolio_value"}))

    by_day = by_day[by_day["date"] <= td].reset_index(drop=True)
    return by_day

def investovany_kapital(target_date, df):
    def _s_to_naive(s):
        s = pd.to_datetime(s, errors="coerce", utc=True)
        return s.dt.tz_convert(None).dt.normalize()
    def _ts_to_naive(ts):
        ts = pd.to_datetime(ts, errors="coerce", utc=True)
        return ts.tz_convert(None).normalize() if pd.notna(ts) else pd.NaT
    # stejné datumové sjednocení jako jinde
    td = _ts_to_naive(target_date)

    dfx = df.copy()
    dfx["Date"] = _s_to_naive(dfx["Date"])
    dfx = dfx.query("Date <= @td")

    # očista částek
    amt = (dfx["Total Amount"].astype(str)
             .str.replace("€", "", regex=False)
             .str.replace(",", "", regex=False)
             .str.replace("-", "", regex=False))
    dfx["Total_clean"] = pd.to_numeric(amt, errors="coerce")
    dfx["Total_clean"] = np.where(dfx["Type"].eq("SELL - MARKET"),
                                 -dfx["Total_clean"], dfx["Total_clean"])
    # masky
    m_topup    = dfx["Type"].eq("CASH TOP-UP")
    m_withdraw = dfx["Type"].eq("CASH WITHDRAWAL")

    topups     = dfx.loc[m_topup, "Total_clean"].sum()
    withdrawals= dfx.loc[m_withdraw, "Total_clean"].sum()

    # netto příspěvky = vklady - výběry
    net_invested = float((topups - withdrawals).round(2))
    return net_invested

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
    base = df[df["Type"].isin(["BUY - MARKET", "SELL - MARKET"])].copy()
    if base.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])

    # --- NOVÉ: sjednocení dat ---
    base["Date"] = _to_naive_day(base["Date"])

    base["Quantity"] = pd.to_numeric(base["Quantity"], errors="coerce").fillna(0.0)
    base["Total_quant_clean"] = np.where(base["Type"].eq("SELL - MARKET"),
                                         -base["Quantity"], base["Quantity"])
    base = base.sort_values(["Ticker", "Date"])
    base["CumulativeShares"] = base.groupby("Ticker", sort=False)["Total_quant_clean"].cumsum()
    base = base[["Date", "Ticker", "CumulativeShares"]]

    min_date = base["Date"].min()
    if pd.isna(min_date):
        return pd.DataFrame(columns=["date", "portfolio_value"])

    dfp = df_prices.copy()
    dfp["date"] = _to_naive_day(dfp["date"])         # --- NOVÉ ---
    dfp = dfp[dfp["date"] >= min_date].drop_duplicates(subset=["date","Ticker_clean"])

    final = pd.merge(
        dfp, base,
        left_on=["date","Ticker_clean"],
        right_on=["Date","Ticker"],
        how="left",
    ).sort_values(["Ticker_clean","date"])

    final["CumulativeShares"] = final.groupby("Ticker_clean", sort=False)["CumulativeShares"].ffill().fillna(0.0)
    final["adjusted_close"] = pd.to_numeric(final["adjusted_close"], errors="coerce").fillna(0.0)

    final["position_value"] = final["CumulativeShares"] * final["adjusted_close"]
    by_day = (final.groupby("date", as_index=False)["position_value"]
                    .sum()
                    .rename(columns={"position_value":"portfolio_value"}))
    return by_day


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




# ---------------------------------------------------------------------------
# 1) Podíl aktiva v portfoliu (pie chart aktiv)
# ---------------------------------------------------------------------------
@callback(
    Output("vystup-div", "figure"),
    Input("vyber-datum", "date"),
    Input('stored-data', 'data')
)
def spust_sjednoceni(vybrane_datum, stored_data):
    if vybrane_datum is None:
        return _msg_figure("Vyber datum pro výpočet portfolia.")
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
        
    else:
        df = df_default

    try:
        
        target_date = pd.to_datetime(vybrane_datum).tz_localize("UTC")
        result_df = sjednoceni(target_date, df)

        fig = px.pie(result_df, values="Total_value", names="Ticker")
        fig.update_layout(showlegend=False)
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=500,
            margin=dict(t=40, b=40, l=40, r=40),
            title=dict(
                text="Podíl aktiva v portfoliu",
                y=1, x=0.5, xanchor='center', yanchor='top',
                font=dict(size=24, color='white', family='Arial')
            )
        )
        fig.update_traces(textposition='inside', textinfo='percent+label+value')
        return fig

    except Exception as e:
        return _msg_figure(f"Chyba: {e}")

# ---------------------------------------------------------------------------
# 2) Pasivní příjmy a výdaje (pie chart)
# ---------------------------------------------------------------------------
@callback(
    Output("vystup_fee_div", "figure"),
    Input("vyber-datum", "date"),
    Input('stored-data', 'data')
)
def vypocitat_fees_divi(vybrane_datum, stored_data):
    if vybrane_datum is None:
        return _msg_figure("Vyber datum pro výpočet portfolia.")
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default

    try:
        target_date = pd.to_datetime(vybrane_datum).tz_localize("UTC")
        result_df = fees_divi(target_date, df)

        fig = px.pie(result_df, values="Total_money", names="Type")
        fig.update_layout(showlegend=False)
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=500,
            margin=dict(t=40, b=40, l=40, r=40),
            title=dict(
                text="Pasivní příjmy a výdaje portfolia",
                y=1, x=0.5, xanchor='center', yanchor='top',
                font=dict(size=24, color='white', family='Arial')
            )
        )
        fig.update_traces(textposition='inside', textinfo='percent+label+value')
        return fig

    except Exception as e:
        return _msg_figure(f"Chyba: {e}")

# ---------------------------------------------------------------------------
# 3) Souhrnná tabulka portfolia
# ---------------------------------------------------------------------------
@callback(
    Output("vystup_tabulka_portfolio", "children"),
    Input("vyber-datum", "date"),
    Input('stored-data', 'data')
)
def vypocitat_hlavni_tabulku(vybrane_datum, stored_data):
    if vybrane_datum is None:
        return "Vyber datum pro výpočet portfolia."
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default
    

    try:
        tickers = set(df["Ticker"])
        prices = df_prices_all.query("Ticker_clean in @tickers")
        target_date = pd.to_datetime(vybrane_datum).tz_localize("UTC")
        result_df    = sjednoceni(target_date, df)
        result_price = soucasna_cena(target_date, prices)
        result_divi  = vypocet_dividend(target_date, df)

        result_df["Avg_purch_price"] = (result_df["Total_value"] / result_df["Total_quantity"]).round(2)
        result_df["Total_value"]     = result_df["Total_value"].round(2)
        result_df["Total_purch_val"] = result_df["Total_value"]
        result_df["Total_quantity"]  = result_df["Total_quantity"].round(2)

        final_df = pd.merge(result_df, result_price, left_on="Ticker", right_on="Ticker_clean", how="left")
        final_df = pd.merge(final_df, result_divi, on="Ticker", how="left")
        final_df["Total_curr_val"] = (final_df["Total_quantity"] * final_df["adjusted_close"]).round(2)
        final_df["Total_money"]    = final_df["Total_money"].fillna(0).round(2)
        final_df["Profit"]         = (final_df["Total_curr_val"] - final_df["Total_purch_val"] + final_df["Total_money"]).round(2)
        final_df["Dividenda"]      = final_df["Total_money"]

        final_df = final_df[[
            "Ticker", "Total_purch_val", "Total_curr_val",
            "Total_quantity", "Avg_purch_price", "Dividenda", "Profit"
        ]]
        final_df = final_df.rename(columns = {"Ticker":"TICKER","Total_purch_val":"CELKOVÁ KUPNÍ HODNOTA","Total_curr_val":"CELKOVÁ SOUČASNÁ HODNOTA",
                                               "Total_quantity":"CELKOVÝ POČET","Avg_purch_price":"PRŮMĚRNÁ NÁKUPNÍ CENA","Dividenda":"DIVIDENDA","Profit":"PROFIT" })

        return dash_table.DataTable(
            columns=[{"name": c, "id": c} for c in final_df.columns],
            data=final_df.to_dict("records"),
            style_table={"overflowX": "auto"},
            style_cell={
                "textAlign": "left",
                "backgroundColor": "#1e1e1e",
                "color": "white",
                "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
            },
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
@callback(
    Output("vystup_zaklad_tabulka", "children"),
    Input("vyber-datum", "date"),
    Input('stored-data', 'data')
)
def vypocitat_celkovy_profit(vybrane_datum, stored_data):
    if vybrane_datum is None:
        return "Vyber datum pro výpočet portfolia."
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default

    try:
        tickers = set(df["Ticker"])
        prices = df_prices_all.query("Ticker_clean in @tickers")
        target_date = _to_naive_ts(vybrane_datum)

        result_df    = sjednoceni(target_date, df)
        result_price = soucasna_cena(target_date, prices)
        result_fee   = celkove_fee_divi(target_date, df)
        by_day       = hodnota_portfolia_v_case_tabulka(target_date, df, prices)

        if by_day.empty:
            pv = 0.0
            kapital = float(vypocitat_nevyuzity_kapital(target_date, df))
            hodnota_portfolia = round(pv + kapital, 2)
        else:
            by_day["date"] = pd.to_datetime(by_day["date"], utc=True).dt.tz_convert(None).dt.normalize()
            last_date = by_day["date"].max()
            pv = float(by_day.loc[by_day["date"].eq(last_date), "portfolio_value"].iloc[0])
            kapital = float(vypocitat_nevyuzity_kapital(last_date, df))
            hodnota_portfolia = round(pv + kapital, 2)

        celkem_investovano = investovany_kapital(target_date, df)
        celkovy_profit = round((pv + kapital) - celkem_investovano, 2)
        roi = round(((celkovy_profit / celkem_investovano) * 100), 2) if celkem_investovano else 0.0
        str_roi = f"{roi}%"

        vystup = pd.DataFrame({
            "CELKOVÁ HODNOTA PORTFOLIA": [hodnota_portfolia],
            "CELKOVĚ INVESTOVÁNO": [celkem_investovano],
            "CELKOVÝ VÝNOS PORTFOLIA": [celkovy_profit],
            "ROI": [str_roi]
        })

        if pd.notna(celkovy_profit) and celkovy_profit >= 0:
            barva = "rgba(0, 128, 0, 0.8)" 
        else:
            barva = "rgba(255, 0, 0, 0.8)" 

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
# 5) Ukazatele rizika – tabulka
# ---------------------------------------------------------------------------
@callback(
    Output("pano", "children"),
    Input("vyber-datum", "date"),
    Input('stored-data', 'data')
)
def vypocitat_pano(vybrane_datum, stored_data):
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default
    tickers = set(df["Ticker"])
    prices = df_prices_all.query("Ticker_clean in @tickers")
    target_date = pd.to_datetime(vybrane_datum)
    dfp = prices.sort_values(["Ticker_clean", "date"]).copy()
    dfp["date"] = pd.to_datetime(dfp["date"])
    dfp = dfp.query("date <= @target_date")
    dfp["Return"] = dfp.groupby("Ticker_clean")["adjusted_close"].pct_change()

    risk_free_rate = 0.042
    pano_vysledky = []

    for ticker, group in dfp.groupby("Ticker_clean"):
        returns = group["Return"].dropna()
        if returns.empty:
            continue

        mean_return = returns.mean()
        std_return  = returns.std()

        negativni_odchylky = returns[returns < mean_return]
        ps = len(negativni_odchylky)
        pano = (abs(negativni_odchylky - mean_return).sum()) / ps if ps > 0 else 0.0

        annual_return = mean_return * 252
        annual_volatility = std_return * np.sqrt(252)
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0.0

        downside_returns = returns[returns < (risk_free_rate / 252)]
        downside_deviation = downside_returns.std()
        annual_downside_deviation = downside_deviation * np.sqrt(252)
        sortino_ratio = (annual_return - risk_free_rate) / annual_downside_deviation if annual_downside_deviation != 0 else 0.0

        pano_vysledky.append({
            "Ticker": ticker,
            "Volatilita": round(std_return, 6),
            "Sharpe Ratio": round(sharpe_ratio, 6),
            "Sortino Ratio": round(sortino_ratio, 6),
            "PANO_Hodnota": round(pano, 6),
        })

    pano_df = pd.DataFrame(pano_vysledky).sort_values(by="PANO_Hodnota")

    return dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in pano_df.columns],
        data=pano_df.to_dict("records"),
        style_table={"overflowX": "auto"},
        style_cell={
            "textAlign": "left",
            "backgroundColor": "#1e1e1e",
            "color": "white",
            "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
        },
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
# 6) Heatmapa rizik (korelace)
# ---------------------------------------------------------------------------
@callback(
    Output("risk-heatmap", "figure"),
    Input("vyber-datum", "date"),
    Input('stored-data', 'data')
)
def zobrazit_heatmapu(vybrane_datum, stored_data):
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default
    tickers = set(df["Ticker"])
    prices = df_prices_all.query("Ticker_clean in @tickers")
    target_date = pd.to_datetime(vybrane_datum)
    dfp = prices.sort_values(["Ticker_clean", "date"]).copy()
    dfp["date"] = pd.to_datetime(dfp["date"])
    dfp = dfp.query("date <= @target_date")
    dfp["Return"] = dfp.groupby("Ticker_clean")["adjusted_close"].pct_change()

    risk_free_rate = 0.02
    pano_vysledky = []

    for ticker, group in dfp.groupby("Ticker_clean"):
        returns = group["Return"].dropna()
        if returns.empty:
            continue

        mean_return = returns.mean()
        std_return  = returns.std()

        negativni_odchylky = returns[returns < mean_return]
        ps = len(negativni_odchylky)
        pano = (abs(negativni_odchylky - mean_return).sum()) / ps if ps > 0 else 0.0

        annual_return = mean_return * 252
        annual_volatility = std_return * np.sqrt(252)
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0.0

        downside_returns = returns[returns < (risk_free_rate / 252)]
        downside_deviation = downside_returns.std()
        annual_downside_deviation = downside_deviation * np.sqrt(252)
        sortino_ratio = (annual_return - risk_free_rate) / annual_downside_deviation if annual_downside_deviation != 0 else 0.0

        pano_vysledky.append({
            "Ticker": ticker,
            "PANO": pano,
            "Volatilita": std_return,
            "Sharpe": sharpe_ratio,
            "Sortino": sortino_ratio
        })

    pano_df = pd.DataFrame(pano_vysledky)
    if pano_df.empty:
        return _msg_figure("Nedostatek dat pro korelaci.")

    korelace = pano_df.drop(columns=["Ticker"]).corr()

    fig = px.imshow(
        korelace,
        text_auto=".2f",
        color_continuous_scale="RdBu_r",
        aspect="auto",
        x=korelace.columns,
        y=korelace.columns,
        title="Korelační matice rizikových ukazatelů"
    )
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color="white",
        height=500,
        width=500,
        title=dict(
            text="Korelační matice rizikových ukazatelů portfolia",
            font=dict(size=24, color='white', family='Arial'),
            x=0.5, xanchor='center'
        )
    )
    return fig

# ---------------------------------------------------------------------------
# 7) Graf vývoje ceny vybraných aktiv
# ---------------------------------------------------------------------------
@callback(
    Output("price-graph", "figure"),
    Input("ticker-dropdown", "value"),
    Input("vyber-start_date", "date"),
    Input('stored-data', 'data')
)
def single_performance_graph(selected_tickers, selected_start_date, stored_data):
    if not selected_tickers:
        return _msg_figure("Nebyla vybrána žádná aktiva.")
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default
    tickers = set(df["Ticker"])
    prices = df_prices_all.query("Ticker_clean in @tickers")
    if selected_start_date is None:
        target_date = pd.to_datetime(prices["date"]).max()
    else:
        target_date = pd.to_datetime(selected_start_date)
        if target_date.tzinfo is not None:
            target_date = target_date.tz_convert(None) if target_date.tzinfo else target_date.tz_localize(None)

    filtered_data = prices.query("Ticker_clean in @selected_tickers").copy()
    filtered_data["date"] = pd.to_datetime(filtered_data["date"])
    normalized_df = filtered_data.sort_values(["Ticker_clean", "date"])
    normalized_df = normalized_df[normalized_df["date"] >= target_date]
    first_prices = normalized_df.groupby("Ticker_clean")["adjusted_close"].transform("first")

    normalized_df["normalized_price"] = (normalized_df["adjusted_close"] / first_prices) * 100

    fig = px.line(
        normalized_df,
        x="date", y="normalized_price", color="Ticker_clean",
        labels={"normalized_price": "Indexovaná cena", "Ticker_clean": "Ticker"},
        title="Relativní vývoj cen (počátek = 100)"
    )
    fig.update_layout(
        showlegend=True,
        legend=dict(title="Aktiva", bgcolor="rgba(0, 0, 0, 0.2)", font=dict(color='white')),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#303030',
        height=500,
        margin=dict(t=40, b=40, l=40, r=40),
        title=dict(text="Relativní vývoj cen aktiv portfolia (počátek = 100)",
                   y=1, x=0.5, xanchor='center', yanchor='top',
                   font=dict(size=24, color='white', family='Arial')),
        xaxis=dict(title=dict(text="Datum", font=dict(size=18, color='white', family='Arial')),
                   tickfont=dict(color='white', family='Arial'),
                   showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1),
        yaxis=dict(title=dict(text="Indexovaná cena", font=dict(size=18, color='white', family='Arial')),
                   tickfont=dict(color='white', family='Arial'),
                   showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1),
        shapes=[dict(type="line", xref="paper", x0=0, x1=1, yref="y", y0=100, y1=100,
                     line=dict(color="white", width=1, dash="dot"))],
    )
    return fig

# ---------------------------------------------------------------------------
# 8) Porovnání s benchmarky
# ---------------------------------------------------------------------------
@callback(
    Output("compare_graph", "figure"),
    Input("compare_tickers", "value"),
    State("stored-data", "data")  # <- Store, kde máš nahrané portfolio (JSON)
)
def compare_graph(selected_bench, stored_data):
    try:
        if stored_data is not None:
            if isinstance(stored_data, str):
                df_local = pd.read_json(stored_data, orient="split")
            else:
                df_local = pd.DataFrame(stored_data)
        else:
            df_local = df_default.copy()
    except Exception:
        df_local = df_default.copy()

    tickers_clean = (
        df_local["Ticker"].astype(str).str.split(".").str[0].dropna().unique().tolist()
        if not df_local.empty else []
    )
    prices_filtered = df_prices_all[df_prices_all["Ticker_clean"].isin(tickers_clean)].copy()

    twr_df = twr_index_from_df(df_local, prices_filtered, base=100.0)

    default_benchmarks = ["SXR8"]
    if not selected_bench:
        bench_tickers = default_benchmarks
    else:
        if isinstance(selected_bench, str):
            selected_bench = [selected_bench]
        bench_tickers = sorted(set(selected_bench).union(default_benchmarks))

    bench = make_benchmark_series(
        twr_df, df_prices_all, bench_tickers,
        date_col="date", ticker_col="Ticker_clean",
        price_col="adjusted_close", base=100.0
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=twr_df["date"], y=twr_df["twr_index"],
        mode="lines", name="Portfolio (TWR = 100)",
        line=dict(color="#00ff32", width=2), connectgaps=False
    ))

    for name, s in bench.items():
        s = s.reindex(twr_df["date"].values)
        fig.add_trace(go.Scatter(
            x=twr_df["date"], y=s.values, mode="lines", name=f"{name} (=100)",
            connectgaps=False
        ))

    fig.update_layout(
        autosize=True, height=500,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#303030",
        margin=dict(t=40, b=40, l=40, r=40),
        title=dict(text="Normalizovaná hodnota portfolia + porovnání",
                   y=1, x=0.5, xanchor="center", yanchor="top",
                   font=dict(size=24, color="white", family="Arial")),
        xaxis=dict(title=dict(text="Datum", font=dict(size=18, color="white", family="Arial")),
                   tickfont=dict(color="white", family="Arial"),
                   showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1),
        yaxis=dict(title=dict(text="Index (base = 100)", font=dict(size=18, color="white", family="Arial")),
                   tickfont=dict(color="white", family="Arial"),
                   showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1),
        showlegend=True,
        legend=dict(title="Aktiva", bgcolor="rgba(0, 0, 0, 0.2)", font=dict(color='white')),
        shapes=[dict(type="line", xref="paper", x0=0, x1=1, yref="y", y0=100, y1=100,
                     line=dict(color="white", width=1, dash="dot"))]
    )
    return fig


# ---------------------------------------------------------------------------
# 9) Hodnota portfolia v čase (Daily/Monthly)
# ---------------------------------------------------------------------------
@callback(
    Output("portfolio_v_case", "children"),
    Input("frequency-dropdown", "value"),
    Input("vyber-datum", "date"),
    Input('stored-data', 'data')
)
def graf_portfolio_v_case(freq, vybrane_datum, stored_data):
    if vybrane_datum is None:
        return "Vyber datum pro výpočet portfolia."
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default

    try:
        tickers = set(df["Ticker"])
        prices = df_prices_all.query("Ticker_clean in @tickers")
        target_date = pd.to_datetime(vybrane_datum).tz_localize(None)
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
            return "Žádná platná data pro zadané datum."

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df["date"],
            y=plot_df["portfolio_value"],
            mode="lines",
            name="Portfolio",
            line=dict(color="#00ff32", width=2),
            fill="tozeroy",
            fillcolor="rgba(0, 255, 50, 0.2)",
            connectgaps=False
        ))

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='#303030',
            height=500,
            margin=dict(t=40, b=40, l=40, r=40),
            title=dict(
                text="Hodnota portfolia v čase",
                y=1, x=0.5, xanchor='center', yanchor='top',
                font=dict(size=24, color='white', family='Arial')
            ),
            xaxis=dict(
                title=dict(text="Datum", font=dict(size=18, color='white', family='Arial')),
                tickfont=dict(color='white', family='Arial'),
                showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1
            ),
            yaxis=dict(
                title=dict(text="Hodnota (EUR)", font=dict(size=18, color='white', family='Arial')),
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
@callback(
    Output("monthly-dividends-graph", "figure"),
    Input("stored-data", "data"),
    Input("vyber-datum", "date"),
)
def monthly_dividends_graph(stored_data, _selected_date):
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

    if isinstance(stored_data, list):
        df_local = pd.DataFrame(stored_data)
    elif isinstance(stored_data, dict) and stored_data.get("records"):
        df_local = pd.DataFrame(stored_data["records"])
    elif stored_data is None:
        df_local = df_default.copy()
    else:
        df_local = pd.DataFrame(stored_data)

    required = {"Type", "Date", "Total Amount"}
    if df_local.empty or not required.issubset(set(df_local.columns)):
        return _placeholder("Chybi data pro vypocet mesicnich dividend.")

    all_dates = pd.to_datetime(df_local["Date"], errors="coerce", utc=True).dt.tz_convert(None).dropna()
    if all_dates.empty:
        return _placeholder("Chybi validni datumy pro timeline.")

    month_start = all_dates.min().to_period("M").to_timestamp()
    month_end = all_dates.max().to_period("M").to_timestamp()
    full_months = pd.DataFrame({"month": pd.date_range(month_start, month_end, freq="MS")})

    div = df_local[df_local["Type"].astype(str).str.contains("DIVIDEND", na=False)].copy()
    if div.empty:
        monthly = full_months.copy()
        monthly["Total_clean"] = 0.0
    else:
        div["Date"] = pd.to_datetime(div["Date"], errors="coerce", utc=True).dt.tz_convert(None)
        div["Total_clean"] = _parse_money_series(div["Total Amount"])
        div = div.dropna(subset=["Date", "Total_clean"])
        if div.empty:
            monthly = full_months.copy()
            monthly["Total_clean"] = 0.0
        else:
            div["month"] = div["Date"].dt.to_period("M").dt.to_timestamp()
            monthly = div.groupby("month", as_index=False)["Total_clean"].sum().sort_values("month")
            monthly = full_months.merge(monthly, on="month", how="left").fillna({"Total_clean": 0.0})

    fig = go.Figure(
        data=[
            go.Bar(
                x=monthly["month"],
                y=monthly["Total_clean"],
                marker_color="#00a17b",
                width=1000 * 60 * 60 * 24 * 20,  # fixed ~20-day width to avoid edge stretching
                name="Dividendy",
            )
        ]
    )
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#303030',
        height=500,
        margin=dict(t=40, b=40, l=40, r=40),
        title=dict(
            text="Mesicni dividendovy prijem",
            y=1, x=0.5, xanchor='center', yanchor='top',
            font=dict(size=24, color='white', family='Arial')
        ),
        xaxis=dict(
            title=dict(text="Mesic", font=dict(size=18, color='white', family='Arial')),
            tickfont=dict(color='white', family='Arial'),
            showgrid=True, gridcolor='rgba(255,255,255,0.1)', gridwidth=1,
            type="date",
            dtick="M1",
            tickformat="%Y-%m",
        ),
        yaxis=dict(
            title=dict(text="Castka", font=dict(size=18, color='white', family='Arial')),
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

@callback(
    Output('stored-data', 'data'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def upload_and_store(contents, filename):
    if contents is None:
        return dash.no_update

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), sep=',') #!!!!!! Zatím funguje jenom na čárky ZMĚNIT!!!!!
    
    return df.to_dict('records')
 

layout = html.Div(
    className="home-page",
    children=[
        html.Div(
            className="top-bar",
            children=[
                dcc.DatePickerSingle(
                    id="vyber-datum",
                    date=date.today(),
                    display_format="DD.MM.YYYY",
                    placeholder="Vyber datum",
                    className="date-picker",
                    style={"background":"transparent"},
                ),

                dcc.Upload(
                    id='upload-data',
                    children=html.Button('Nahrát CSV', className="upload-button"),
                    multiple=False
                ),
            ],
        ),
        #Hrubá oprava
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br(),


        # Nadpis
        html.Div(
            className="hero",
            children=[
                html.H1("Analýza portfolia", className="nadpis"),
                html.P("Školní projekt - testovací verze", className="podnadpis"),
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

                        html.Div(
                            className="dropdown-graph-wrapper",
                            children=[
                                html.H2("Souhrnná tabulka portfolia"),
                                html.Div(id="vystup_tabulka_portfolio"),
                            ],
                        ),

                        html.Div(
                            className="dropdown-graph-wrapper",
                            children=[
                                html.H2("Vyber frekvenci dat:"),
                                dcc.Dropdown(
                                    ['Daily', 'Monthly'],
                                    'Daily',
                                    id='frequency-dropdown',
                                    className="dropdown"
                                ),
                                html.Div(id="portfolio_v_case"),
                            ],
                        ),

                        html.Div(
                            className="dropdown-graph-wrapper",
                            children=[
                                html.H2("Ukazatele rizika"),
                                html.Div(id="pano", className="modern-table"),
                            ],
                        ),

                        html.Div(
                            className="dropdown-graph-wrapper",
                            children=[
                                html.H2("Vyber aktiva:"),
                                dcc.Dropdown(
                                    tickers_l,
                                    tickers_l_default,
                                    id='ticker-dropdown',
                                    multi=True,
                                    className="dropdown"
                                ),

                                html.H2("Vyber počáteční datum:"),
                                dcc.DatePickerSingle(
                                    id="vyber-start_date",
                                    date=min(df_prices["date"]),
                                    display_format="DD.MM.YYYY",
                                    placeholder="Vyber datum",
                                ),
                                dcc.Graph(id="price-graph", className="graph"),
                            ],
                        ),

                        html.Div(
                            className="dropdown-graph-wrapper",
                            children=[
                                html.H2("Vyber aktiva na porovnání:"),
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

                        html.Div(
                            className="dropdown-graph-wrapper",
                            children=[
                                html.Div(
                                    className="row-container",
                                    children=[
                                        dcc.Graph(id="vystup-div", className="mini-graph"),
                                        dcc.Graph(id="risk-heatmap", className="mini-graph"),
                                        dcc.Graph(id="vystup_fee_div", className="mini-graph"),
                                    ],
                                )
                            ],
                        ),
                        html.Div(
                            className="dropdown-graph-wrapper",
                            children=[
                                html.H2("Dividendy po mesicich"),
                                dcc.Graph(id="monthly-dividends-graph", className="graph"),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ],
)


