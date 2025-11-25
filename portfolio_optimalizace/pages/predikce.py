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
import sklearn
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt

from statsmodels.tsa.arima.model import ARIMA
from statsmodels.stats.stattools import jarque_bera
from statsmodels.stats.diagnostic import het_arch, acorr_ljungbox
from scipy.stats import shapiro
dash.register_page(__name__, path="/predikce")

df_fallback = pd.read_csv("portfolio.csv", sep=None, engine="python")
df = df_fallback.copy()
df_default = df.copy()
tickers = set(df["Ticker"])
df_prices = pd.read_csv("df_prices.csv")
df_prices_all = pd.read_csv("df_prices.csv")
df_prices["Ticker_clean"] = df_prices["Ticker"].str.split(".").str[0]
df_prices_all = df_prices.copy()

hodnotici_kriteria = ["RMSE","AIC","BIC"]

def hodnota_portfolia_v_case(df, df_prices):
    df = df.sort_values(by="Date")
    df = df[df["Type"].isin(["BUY - MARKET", "SELL - MARKET"])]

    df_copy = df.copy()
    df_copy["Total_clean"] = (
        df_copy["Total Amount"].astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
        .astype(float)
    )
    df_copy["Total_quant_clean"] = np.where(
        df_copy["Type"] == "SELL - MARKET",
        -df_copy["Quantity"],
        df_copy["Quantity"]
    )
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

    final["CumulativeShares"] = final["CumulativeShares"].fillna(0)

    final["position_value"] = final["CumulativeShares"] * final["adjusted_close"]
    final["portfolio_value"] = final.groupby("date")["position_value"].transform("sum")

    pos_mask = final["portfolio_value"] > 0
    if pos_mask.any():
        first_valid_date = final.loc[pos_mask, "date"].min()
        final = final[final["date"] >= first_valid_date]

    final = final.reset_index(drop=True)

    return final

def split_by_ticker(df, test_size=0.2):
    df = df.sort_values("date")
    result = {}
    
    for ticker, group in df.groupby("Ticker_clean"):
        group = group.reset_index(drop=True)
        split_idx = int(len(group) * (1 - test_size))
        train = group.iloc[:split_idx]
        test = group.iloc[split_idx:]
        result[ticker] = {"train": train, "test": test}
    
    return result


def logy(series):
    return np.log(series +1e-10).diff().fillna(0)

def train_test_split_series(series: pd.Series, test_size: float = 0.2):
    split_idx = int(len(series) * (1 - test_size))
    train = series.iloc[:split_idx]
    test = series.iloc[split_idx:]
    return train, test

def rmse(y_true, y_pred) -> float:
    return float(np.sqrt(np.mean((np.array(y_true) - np.array(y_pred)) ** 2)))

def grid_search_arima(
    train: pd.Series,
    test: pd.Series,
    p_range=range(0, 4),
    d_range=range(0, 1),
    q_range=range(0, 4),
):
    results = []
    best_rmse = np.inf
    best_order = None
    best_model = None

    for p in p_range:
        for d in d_range:
            for q in q_range:
                order = (p, d, q)
                try:
                    model = ARIMA(train, order=order)
                    model_fit = model.fit()
                    forecast = model_fit.forecast(steps=len(test))
                    score = rmse(test, forecast)

                    results.append(
                        {
                            "order": order,
                            "rmse": score,
                        }
                    )

                    if score < best_rmse:
                        best_rmse = score
                        best_order = order
                        best_model = model_fit
                except Exception as e:

                    results.append(
                        {
                            "order": order,
                            "rmse": np.nan,
                            "error": str(e),
                        }
                    )
                    continue

    results_df = pd.DataFrame(results)
    return best_order, best_rmse, best_model, results_df.sort_values("rmse")


def grid_search_arima_aic(
    train: pd.Series,
    test: pd.Series,  # necháme pro konzistenci signatury, ale nepoužijeme
    p_range=range(0, 4),
    d_range=range(0, 1),
    q_range=range(0, 4),
):
    results = []
    best_aic = np.inf
    best_order = None
    best_model = None

    for p in p_range:
        for d in d_range:
            for q in q_range:
                order = (p, d, q)
                try:
                    model = ARIMA(train, order=order)
                    model_fit = model.fit()
                    score = model_fit.aic

                    results.append(
                        {
                            "order": order,
                            "aic": score,
                        }
                    )

                    if score < best_aic:
                        best_aic = score
                        best_order = order
                        best_model = model_fit
                except Exception as e:
                    results.append(
                        {
                            "order": order,
                            "aic": np.nan,
                            "error": str(e),
                        }
                    )
                    continue

    results_df = pd.DataFrame(results)
    return best_order, best_aic, best_model, results_df.sort_values("aic")


def grid_search_arima_bic(
    train: pd.Series,
    test: pd.Series,  # opět ignorujeme, jen kvůli jednotné signatuře
    p_range=range(0, 4),
    d_range=range(0, 1),
    q_range=range(0, 4),
):
    results = []
    best_bic = np.inf
    best_order = None
    best_model = None

    for p in p_range:
        for d in d_range:
            for q in q_range:
                order = (p, d, q)
                try:
                    model = ARIMA(train, order=order)
                    model_fit = model.fit()
                    score = model_fit.bic

                    results.append(
                        {
                            "order": order,
                            "bic": score,
                        }
                    )

                    if score < best_bic:
                        best_bic = score
                        best_order = order
                        best_model = model_fit
                except Exception as e:
                    results.append(
                        {
                            "order": order,
                            "bic": np.nan,
                            "error": str(e),
                        }
                    )
                    continue

    results_df = pd.DataFrame(results)
    return best_order, best_bic, best_model, results_df.sort_values("bic")


from statsmodels.tsa.seasonal import STL
import numpy as np

def detect_seasonality(series, max_period=365):
    """
    Vrátí odhadnutou sezónní periodu.
    Pokud není silná sezónnost → vrací None.
    """
    series = series.dropna()

    # periodogram
    freqs = np.fft.rfftfreq(len(series))
    spectrum = np.abs(np.fft.rfft(series - np.mean(series)))

    # ignorujeme frekvenci 0 (trend)
    peak_freq = freqs[np.argmax(spectrum[1:]) + 1]

    if peak_freq == 0:
        return None

    period = int(1 / peak_freq)

    if period <= 1 or period > max_period:
        return None

    return period


from statsmodels.tsa.stattools import acf

def detect_seasonality_acf(series, min_lag=2, max_lag=365, threshold=0.2):
    values = series.dropna().values
    acf_vals = acf(values, nlags=max_lag)

    peaks = np.where(acf_vals[min_lag:] > threshold)[0]
    if len(peaks) == 0:
        return None

    return peaks[0] + min_lag


def detect_seasonality_auto(series):
    p1 = detect_seasonality(series)
    p2 = detect_seasonality_acf(series)

    # pokud obě metody souhlasí → vysoká jistota
    if p1 == p2:
        return p1

    # pokud jedna vrátí dobrou sezónnost → použijeme tu
    if p1 is not None:
        return p1
    if p2 is not None:
        return p2

    return None


from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.arima.model import ARIMA

def fit_auto_arima_or_sarima(series, p=3, d=1, q=3):
    
    season = detect_seasonality_auto(series)

    if season is None:
        print("→ ŽÁDNÁ sezónnost → používám ARIMA")
        model = ARIMA(series, order=(p, d, q)).fit()
        return model, None

    else:
        print(f"→ Detekovaná sezónnost: s={season} → používám SARIMA")
        model = SARIMAX(series, order=(p, d, q),
                        seasonal_order=(1, 0, 1, season)
                        ).fit(disp=False)
        return model, season
#########################################################################################x


@callback(
    Output("arima2", "children"),
    Input("ticker_pred", "value"),
    Input("kriteria_pred", "value")
)
def arima_predikce_tickeru(ticker, kriteria):

    if ticker is None:
        return html.Div([
            html.H3("ARIMA/SARIMA predikce akcie"),
            html.P("Vyberte akcii v dropdownu.")
        ])

    if kriteria is None:
        kriteria = "RMSE"

    forecast_steps = 30
    min_obs = 40

    df_t = df_prices_all[df_prices_all["Ticker_clean"] == ticker].copy()
    if df_t.empty:
        return html.Div([html.P(f"Žádná data pro {ticker}.")])

    df_t["date"] = pd.to_datetime(df_t["date"], errors="coerce")
    df_t = df_t.dropna(subset=["date"]).sort_values("date")

    price_series = df_t.set_index("date")["adjusted_close"].astype(float)

    # --- log-returny ---
    log_ret = logy(price_series)
    if len(log_ret) < min_obs:
        return html.Div([
            html.H3(f"ARIMA/SARIMA predikce – {ticker}"),
            html.P(f"{ticker}: málo dat pro ARIMA/SARIMA ({len(log_ret)} log-returnů)."),
            dcc.Graph(
                figure=px.line(
                    df_t, x="date", y="adjusted_close",
                    title=f"Historie ceny – {ticker}"
                )
            )
        ])

    # --- train/test split ---
    train, test = train_test_split_series(log_ret, test_size=0.2)

    # --- GRID SEARCH ---
    if kriteria == "RMSE":
        best_order, best_score, best_model, _ = grid_search_arima(train, test)
        score_name = "RMSE"
    elif kriteria == "AIC":
        best_order, best_score, best_model, _ = grid_search_arima_aic(train, test)
        score_name = "AIC"
    else:
        best_order, best_score, best_model, _ = grid_search_arima_bic(train, test)
        score_name = "BIC"

    if best_order is None:
        return html.Div([
            html.H3(f"Predikce – {ticker}"),
            html.P("Model nebyl nalezen.")
        ])

    # --- DETEKCE SEZÓNOSTI ---
    season_period = detect_seasonality_acf(log_ret, max_lag=252, threshold=0.2)
    log_ret_clean = log_ret.reset_index(drop=True)

    if season_period is None:
        final_model = ARIMA(log_ret_clean, order=best_order).fit()
        model_label = f"ARIMA{best_order}"
    else:
        final_model = SARIMAX(
            log_ret_clean,
            order=best_order,
            seasonal_order=(1, 0, 0, season_period)
        ).fit(disp=False)
        model_label = f"SARIMA{best_order}×(1,0,0,{season_period})"

    # --- forecast (log-returny) ---
    future_log_ret = final_model.forecast(steps=forecast_steps)
    cum_log_ret = future_log_ret.cumsum()
    rel_change = np.exp(cum_log_ret)

    last_price = price_series.iloc[-1]
    future_prices = last_price * rel_change

    inferred_freq = pd.infer_freq(price_series.index)
    if inferred_freq is None:
        inferred_freq = "D"

    future_index = pd.date_range(
        start=price_series.index[-1] + pd.tseries.frequencies.to_offset(inferred_freq),
        periods=forecast_steps,
        freq=inferred_freq
    )
    future_prices.index = future_index
    future_log_ret.index = future_index

    # ==========================================================
    # === 1) HLAVNÍ GRAF – ceny (historie + predikce) ==========
    # ==========================================================

    fig_price = go.Figure()

    fig_price.add_trace(go.Scatter(
        x=price_series.index,
        y=price_series.values,
        mode="lines",
        name=f"{ticker} – historie",
        line=dict(width=2)
    ))

    fig_price.add_trace(go.Scatter(
        x=future_prices.index,
        y=future_prices.values,
        mode="lines",
        name=f"{ticker} – predikce",
        line=dict(width=2, dash="dot")
    ))

    fig_price.update_layout(
        showlegend=True,
        legend=dict(bgcolor="rgba(0,0,0,0.2)", font=dict(color="white")),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#303030',
        height=500,
        title=dict(
            text=f"{model_label} – {ticker} ({score_name} = {best_score:.4f})",
            font=dict(size=22, color='white')
        ),
        xaxis=dict(tickfont=dict(color='white'), title="Datum"),
        yaxis=dict(tickfont=dict(color='white'), title="Cena")
    )

    # ==========================================================
    # === 2) NOVÝ GRAF – log-returny ===========================
    # ==========================================================

    fig_lr = go.Figure()

    # historické log-returny
    fig_lr.add_trace(go.Scatter(
        x=log_ret.index,
        y=log_ret.values,
        mode="lines",
        name="Historické log-returny",
        line=dict(width=2, color="#00ff88")
    ))

    # predikované log-returny
    fig_lr.add_trace(go.Scatter(
        x=future_log_ret.index,
        y=future_log_ret.values,
        mode="lines",
        name="Predikované log-returny",
        line=dict(width=2, dash="dot", color="#ffaa00")
    ))

    fig_lr.update_layout(
        showlegend=True,
        legend=dict(bgcolor="rgba(0,0,0,0.2)", font=dict(color="white")),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#303030',
        height=400,
        title=dict(
            text=f"Log-returny – historie a predikce ({model_label})",
            font=dict(size=20, color='white')
        ),
        xaxis=dict(tickfont=dict(color='white'), title="Datum"),
        yaxis=dict(tickfont=dict(color='white'), title="Log-return")
    )

    # ==========================================================

    return html.Div([
        dcc.Graph(figure=fig_price),
        html.Br(),
        dcc.Graph(figure=fig_lr)
    ])






layout = html.Div([
    html.H1("", className = "prazdno"),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Br(),
    html.Br(),
    html.H1("Predikce jednotlivých aktiv a portfolia", className = "nadpis_predikce"),
    
    
    html.Div(
        className="dropdown-graph-wrapper",
        children=[
            html.H2("ARIMA predikce aktiva:"),

            dcc.Dropdown(list(tickers), id='ticker_pred', multi=False, className="dropdown"),
            dcc.Dropdown(hodnotici_kriteria, id='kriteria_pred', multi=False,value=hodnotici_kriteria[0], className="dropdown" ),

            html.Div(id="arima2", className="graph"),
        ]
    )

])
