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

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.stats.stattools import jarque_bera
from statsmodels.stats.diagnostic import het_arch, acorr_ljungbox
from scipy.stats import shapiro
from arch import arch_model

from backend.services.market_data_service import load_market_data
from backend.services.portfolio_service import empty_transactions_dataframe, load_portfolio_transactions_dataframe
from backend.session import get_current_user
from utils.portfolio_history import build_portfolio_value_history, portfolio_tickers

import numpy as np
import pandas as pd

from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import acf
from statsmodels.stats.diagnostic import het_arch

from arch import arch_model


dash.register_page(__name__, path="/predikce")

df_empty = empty_transactions_dataframe()
df_prices = load_market_data().copy()
df_prices_all = load_market_data().copy()
df_prices["Ticker_clean"] = df_prices["Ticker"].str.split(".").str[0]
df_prices_all = df_prices.copy()

HISTORY_COLOR = "#00a17b"
PREDICTION_COLOR = "#f27a1a"
VOLATILITY_COLOR = "#ffd37a"
VOLATILITY_FILL_STRONG = "rgba(255, 211, 122, 0.20)"
VOLATILITY_FILL_SOFT = "rgba(255, 211, 122, 0.10)"


def _get_current_portfolio_df(active_portfolio_data):
    user = get_current_user()
    portfolio_id = (active_portfolio_data or {}).get("portfolio_id") if isinstance(active_portfolio_data, dict) else None
    if user and portfolio_id:
        loaded = load_portfolio_transactions_dataframe(user["id"], portfolio_id, fallback=df_empty)
        return loaded.copy() if isinstance(loaded, pd.DataFrame) else df_empty.copy()
    return df_empty.copy()

hodnotici_kriteria = ["RMSE","AIC","BIC"]

ml_model_options = [
    {"label": "Linear Regression", "value": "LinearRegression"},
    {"label": "Random Forest", "value": "RandomForest"},
    {"label": "Gradient Boosting", "value": "GradientBoosting"},
    {"label": "Neural Network (MLP)", "value": "MLP"},
]

def hodnota_portfolia_v_case(df, df_prices):
    history = build_portfolio_value_history(df, df_prices)
    if history.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])
    return history

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



# =========================================================
# 1) Split + metrika
# =========================================================

def train_test_split_series(series: pd.Series, test_size: float = 0.2):
    series = pd.Series(series).dropna()
    split_idx = int(len(series) * (1 - test_size))
    train = series.iloc[:split_idx]
    test = series.iloc[split_idx:]
    return train, test


def rmse(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


# =========================================================
# 2) Returny
# =========================================================

def log_returns_from_prices(price_series: pd.Series) -> pd.Series:
    """log(P_t) - log(P_{t-1})"""
    s = pd.Series(price_series).astype(float)
    return np.log(s + 1e-12).diff().dropna()


def simple_returns_from_prices(price_series: pd.Series) -> pd.Series:
    """P_t/P_{t-1} - 1"""
    s = pd.Series(price_series).astype(float)
    return s.pct_change().dropna()


def logret_to_price_path(last_price: float, future_log_ret: pd.Series) -> pd.Series:
    """P_{t+h} = P_t * exp(cumsum(logret))"""
    cum = pd.Series(future_log_ret).astype(float).cumsum()
    return float(last_price) * np.exp(cum)


def ret_to_price_path(last_price: float, future_ret: pd.Series) -> pd.Series:
    """P_{t+h} = P_t * cumprod(1 + ret)"""
    r = pd.Series(future_ret).astype(float)
    return float(last_price) * (1.0 + r).cumprod()


# =========================================================
# 3) Detekce sezónnosti (daily data → hledáme periodu v lags)
# =========================================================

def detect_seasonality_fft(series: pd.Series, max_period: int = 365):
    """Rychlý odhad periody přes periodogram (FFT)."""
    s = pd.Series(series).dropna().astype(float)
    if len(s) < 30:
        return None

    freqs = np.fft.rfftfreq(len(s))
    spectrum = np.abs(np.fft.rfft(s - np.mean(s)))

    if len(spectrum) <= 1:
        return None

    peak_freq = freqs[np.argmax(spectrum[1:]) + 1]  # ignorujeme 0
    if peak_freq <= 0:
        return None

    period = int(round(1.0 / peak_freq))
    if period <= 1 or period > max_period:
        return None
    return period


def detect_seasonality_acf(series: pd.Series, min_lag: int = 2, max_lag: int = 365, threshold: float = 0.2):
    """Sezónnost jako první významný peak v ACF nad threshold."""
    s = pd.Series(series).dropna().astype(float)
    if len(s) < max(30, max_lag + 1):
        max_lag = min(max_lag, len(s) - 1)

    if max_lag < min_lag:
        return None

    acf_vals = acf(s.values, nlags=max_lag)
    peaks = np.where(acf_vals[min_lag:] > threshold)[0]
    if len(peaks) == 0:
        return None
    return int(peaks[0] + min_lag)


def detect_seasonality_auto(series: pd.Series, max_period: int = 365, acf_max_lag: int = 365, threshold: float = 0.2):
    p1 = detect_seasonality_fft(series, max_period=max_period)
    p2 = detect_seasonality_acf(series, max_lag=acf_max_lag, threshold=threshold)

    if p1 is not None and p2 is not None and p1 == p2:
        return p1
    return p1 if p1 is not None else p2


# =========================================================
# 4) Grid search ARIMA / SARIMA podle RMSE
# =========================================================

from statsmodels.tsa.stattools import adfuller

def estimate_d_min_adf(series: pd.Series, max_d: int = 2, alpha: float = 0.05) -> int:
    """
    Najde nejmenší d (0..max_d), pro které ADF zamítne jednotkový kořen (p < alpha).
    Vrací d_min; pokud nic nevyjde, vrátí max_d.
    """
    x = pd.Series(series).dropna().astype(float)
    if len(x) < 30:
        return 0  # málo dat -> nechat grid search rozhodnout, ale netlačit d nahoru

    for d in range(0, max_d + 1):
        y = x.diff(d).dropna() if d > 0 else x
        if len(y) < 30:
            continue
        try:
            pval = adfuller(y, autolag="AIC")[1]
            if np.isfinite(pval) and pval < alpha:
                return d
        except Exception:
            continue

    return max_d

def ljung_box_test(residuals, lags=None, alpha=0.05):
    resid = np.asarray(residuals)
    resid = resid[np.isfinite(resid)]
    if resid.size < 20:
        return False, np.nan

    resid = (resid - resid.mean()) / (resid.std() + 1e-12)

    if lags is None:
        lags = min(20, max(5, resid.size // 10))

    lb = acorr_ljungbox(resid, lags=[lags], return_df=True)
    pvalue = float(lb["lb_pvalue"].iloc[0])
    return (pvalue > alpha), pvalue


def grid_search_arima_rmse(
    train: pd.Series,
    test: pd.Series,
    p_range=range(0, 4),
    d_range=range(0, 2),
    q_range=range(0, 4),
    lb_alpha=0.05,
    lb_lags=None,
):
    results = []
    best_rmse = np.inf
    best_order = None

    # fallback best (bez whiteness)
    best_rmse_any = np.inf
    best_order_any = None

    train = pd.Series(train).dropna().astype(float)
    test = pd.Series(test).dropna().astype(float)
    d_min = estimate_d_min_adf(train, max_d=2, alpha=0.05)
    d_range = range(d_min, min(d_min + 2, 3))
    if len(train) < 30 or len(test) < 10:
        return None, np.nan, None, pd.DataFrame()

    for p in p_range:
        for d in d_range:
            for q in q_range:
                order = (p, d, q)
                try:
                    model_fit = ARIMA(train, order=order).fit()

                    forecast = model_fit.forecast(steps=len(test))
                    score = rmse(test.values, forecast.values)

                    resid = model_fit.resid
                    is_white, p_lb = ljung_box_test(resid, lags=lb_lags, alpha=lb_alpha)

                    results.append({
                        "order": order,
                        "rmse": float(score),
                        "ljung_box_ok": bool(is_white),
                        "ljung_box_pvalue": p_lb,
                    })

                    # best overall (fallback)
                    if np.isfinite(score) and score < best_rmse_any:
                        best_rmse_any = score
                        best_order_any = order

                    # best that passes whiteness
                    if np.isfinite(score) and score < best_rmse and is_white:
                        best_rmse = score
                        best_order = order

                except Exception as e:
                    results.append({
                        "order": order,
                        "rmse": np.nan,
                        "ljung_box_ok": None,
                        "ljung_box_pvalue": np.nan,
                        "error": str(e),
                    })

    results_df = pd.DataFrame(results)
    if "rmse" in results_df.columns:
        results_df = results_df.sort_values("rmse", na_position="last")

    # fallback pokud nic neprošlo LB
    if best_order is None:
        best_order, best_rmse = best_order_any, float(best_rmse_any)

    return best_order, float(best_rmse), None, results_df


def grid_search_sarima_rmse(
    train: pd.Series,
    test: pd.Series,
    s: int,
    p_range=range(0, 3),
    d_range=range(0, 2),
    q_range=range(0, 3),
    P_range=range(0, 2),
    D_range=range(0, 2),
    Q_range=range(0, 2),
):
    results = []
    best_rmse = np.inf
    best_order = None
    best_seasonal_order = None
    best_rmse_any = np.inf
    best_order_any = None
    best_seasonal_order_any = None

    train = pd.Series(train).dropna().astype(float)
    test = pd.Series(test).dropna().astype(float)
    d_min = estimate_d_min_adf(train, max_d=2, alpha=0.05)
    d_range = range(d_min, min(d_min + 2, 3))
    D_range = range(0, 2)
    if s is None or s <= 1:
        return None, None, np.nan, None, pd.DataFrame()

    if len(train) < 30 or len(test) < 5:
        return None, None, np.nan, None, pd.DataFrame()

    for p in p_range:
        for d in d_range:
            for q in q_range:
                for P in P_range:
                    for D in D_range:
                        for Q in Q_range:
                            order = (p, d, q)
                            seasonal_order = (P, D, Q, s)
                            try:
                                model = SARIMAX(train, order=order, seasonal_order=seasonal_order)
                                model_fit = model.fit(disp=False)
                                forecast = model_fit.forecast(steps=len(test))
                                score = rmse(test.values, forecast.values)
                                resid = model_fit.resid
                                resid = (resid - resid.mean()) / (resid.std() + 1e-12)
                                is_white, p_lb = ljung_box_test(resid)

                                results.append({"order": order, "seasonal_order": seasonal_order, "rmse": score, "ljung_box_pvalue": p_lb})

                                if np.isfinite(score) and score < best_rmse_any:
                                    best_rmse_any = score
                                    best_order_any = order
                                    best_seasonal_order_any = seasonal_order

                                if np.isfinite(score) and score < best_rmse and is_white == True:
                                    best_rmse = score
                                    best_order = order
                                    best_seasonal_order = seasonal_order

                            except Exception as e:
                                results.append({"order": order, "seasonal_order": seasonal_order, "rmse": np.nan, "error": str(e)})

    results_df = pd.DataFrame(results)
    if "rmse" in results_df.columns:
        results_df = results_df.sort_values("rmse", na_position="last")

    if best_order is None:
        best_order = best_order_any
        best_seasonal_order = best_seasonal_order_any
        best_rmse = float(best_rmse_any)

    return best_order, best_seasonal_order, best_rmse, None, results_df


# =========================================================
# 5) ARCH efekt na reziduích (po mean modelu!)
# =========================================================

def arch_effect_pvalue(residuals: pd.Series, nlags: int = 12) -> float:
    r = pd.Series(residuals).dropna().astype(float)
    if len(r) < nlags + 10:
        return np.nan
    stat, pval, _, _ = het_arch(r.values, nlags=nlags)
    return float(pval)


# =========================================================
# 6) Grid search GARCH podle RMSE na testu
#     RMSE( r_test^2 , sigma2_forecast )
# =========================================================

def grid_search_garch_rmse(
    train: pd.Series,
    test: pd.Series,
    p_range=range(1, 4),
    q_range=range(1, 4),
    dist: str = "normal",
):
    results = []
    best_score = np.inf
    best_order = None

    train = pd.Series(train).dropna().astype(float)
    test = pd.Series(test).dropna().astype(float)

    # často se škáluje na procenta, aby optimalizace byla stabilnější
    # (pro denní returny je to téměř vždy lepší)
    train_s = train * 100.0
    test_s = test * 100.0

    if len(train_s) < 50 or len(test_s) < 10:
        return None, np.nan, None, pd.DataFrame()

    for p in p_range:
        for q in q_range:
            try:
                sigma2_forecasts = []
                history = train_s.copy()
                for observation in test_s.values:
                    am = arch_model(
                        history,
                        mean="Zero",
                        vol="GARCH",
                        p=p,
                        q=q,
                        dist=dist,
                    )
                    res = am.fit(disp="off")
                    fcast = res.forecast(horizon=1, reindex=False)
                    sigma2_next = float(fcast.variance.values[-1, 0])
                    sigma2_forecasts.append(sigma2_next)
                    history = pd.concat([history, pd.Series([observation])], ignore_index=True)

                score = rmse((test_s.values ** 2), np.asarray(sigma2_forecasts, dtype=float))

                results.append({"p": p, "q": q, "rmse": score})

                if np.isfinite(score) and score < best_score:
                    best_score = score
                    best_order = (p, q)

            except Exception as e:
                results.append({"p": p, "q": q, "rmse": np.nan, "error": str(e)})

    results_df = pd.DataFrame(results)
    if "rmse" in results_df.columns:
        results_df = results_df.sort_values("rmse", na_position="last")

    return best_order, best_score, None, results_df


from statsmodels.stats.diagnostic import het_arch
from arch import arch_model
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.arima.model import ARIMA

def detect_arch_effect(residuals: pd.Series, alpha: float = 0.05, lags: int = 12):
    """
    Engle ARCH LM test na reziduích.
    Vrací (has_arch, pvalue, stat).
    """
    r = pd.Series(residuals).dropna().astype(float)
    if len(r) < max(50, lags * 5):
        return False, np.nan, np.nan

    stat, pvalue, _, _ = het_arch(r, nlags=lags)
    return (pvalue < alpha), float(pvalue), float(stat)





def pick_mean_model_rmse(log_ret: pd.Series):
    """
    Automaticky vybere ARIMA nebo SARIMA podle detekce sezónnosti.
    Optimalizuje RMSE na testu.
    Vrací:
      model_fit, model_label, rmse_score, season_period (nebo None)
    """
    train, test = train_test_split_series(log_ret, test_size=0.2)

    season_period = detect_seasonality_acf(log_ret, max_lag=252, threshold=0.2)

    if season_period is None:
        best_order, best_score, _best_model, _ = grid_search_arima_rmse(train, test)
        if best_order is None:
            return None, None, np.nan, None
        final_model = ARIMA(log_ret, order=best_order).fit()
        return final_model, f"ARIMA{best_order}", float(best_score), None

    # SARIMA
    best_order, best_seasonal_order, best_score, _best_model, _ = grid_search_sarima_rmse(
        train, test, s=season_period
    )
    if best_order is None or best_seasonal_order is None:
        return None, None, np.nan, season_period

    final_model = SARIMAX(log_ret, order=best_order, seasonal_order=best_seasonal_order).fit(disp=False)
    return final_model, f"SARIMA{best_order}×{best_seasonal_order}", float(best_score), season_period


def returns_to_price_path(last_price: float, future_log_ret: pd.Series) -> pd.Series:
    """
    Z log-returnů udělá cenovou cestu.
    P_{t+h} = P_t * exp(sum_{i=1..h} r_{t+i})
    """
    cum = future_log_ret.cumsum()
    path = last_price * np.exp(cum)
    return pd.Series(path.values, index=future_log_ret.index, name="price_pred")


def make_future_index(price_index: pd.DatetimeIndex, steps: int) -> pd.DatetimeIndex:
    inferred_freq = pd.infer_freq(price_index)
    if inferred_freq is None:
        inferred_freq = "D"
    start = price_index[-1] + pd.tseries.frequencies.to_offset(inferred_freq)
    return pd.date_range(start=start, periods=steps, freq=inferred_freq)


def sigma_to_price_bands(last_price: float, future_log_ret: pd.Series, sigma: pd.Series, k: float = 1.0):
    """
    Přepočet 1-step volatility na korektnější více-krokové pásmo.
    Pro horizont h používáme:
      mean_cum_h = sum_{i=1..h} mu_i
      var_cum_h  = sum_{i=1..h} sigma_i^2
    a pak:
      upper_h = P_t * exp(mean_cum_h + k * sqrt(var_cum_h))
      lower_h = P_t * exp(mean_cum_h - k * sqrt(var_cum_h))
    """
    sigma = sigma.reindex(future_log_ret.index).astype(float)
    mu_cum = future_log_ret.astype(float).cumsum()
    var_cum = sigma.pow(2).cumsum()
    std_cum = np.sqrt(var_cum)
    upper = float(last_price) * np.exp(mu_cum + k * std_cum)
    lower = float(last_price) * np.exp(mu_cum - k * std_cum)
    return lower.rename("lower_band"), upper.rename("upper_band")


def forecast_sigma_series(residuals: pd.Series, future_index: pd.DatetimeIndex, forecast_steps: int):
    sigma_future = pd.Series(np.full(forecast_steps, np.nan), index=future_index, name="sigma")
    garch_label = "NO-GARCH"
    garch_rmse = np.nan

    has_arch, arch_p, arch_stat = detect_arch_effect(residuals, alpha=0.05, lags=12)
    if not has_arch:
        return sigma_future, garch_label, garch_rmse, arch_p, arch_stat

    resid_series = pd.Series(residuals).dropna().astype(float)
    train_r, test_r = train_test_split_series(resid_series, test_size=0.2)
    best_pq, garch_rmse, _garch_model, _ = grid_search_garch_rmse(
        train_r,
        test_r,
        p_range=range(1, 4),
        q_range=range(1, 4),
    )
    if best_pq is None:
        return sigma_future, garch_label, garch_rmse, arch_p, arch_stat

    p_opt, q_opt = best_pq
    garch_label = f"GARCH{best_pq}"
    scaled_resid = resid_series * 100.0
    am = arch_model(scaled_resid, mean="Zero", vol="GARCH", p=p_opt, q=q_opt, dist="normal")
    res = am.fit(disp="off")
    fcast = res.forecast(horizon=forecast_steps, reindex=False)
    sigma2 = fcast.variance.values[-1, :]
    sigma_future = pd.Series(np.sqrt(sigma2) / 100.0, index=future_index, name="sigma")
    return sigma_future, garch_label, garch_rmse, arch_p, arch_stat


#########################################################################################x#########################################################################################x

#########################################################################################x
#########################################################################################x
#########################################################################################x
#########################################################################################x
#########################################################################################x
#########################################################################################x
#########################################################################################x
@callback(
    Output("ticker_pred", "options"),
    Output("ticker_pred", "value"),
    Input("active-portfolio-store", "data")
)
def update_ticker_dropdown(active_portfolio_data):
    df_uploaded = _get_current_portfolio_df(active_portfolio_data)
    if df_uploaded.empty or "Ticker" not in df_uploaded.columns:
        return [], None
    tickers_uploaded = sorted(portfolio_tickers(df_uploaded))
    if len(tickers_uploaded) > 0:
        return (
            [{"label": t, "value": t} for t in tickers_uploaded],
            None
        )
    return [], None




@callback(
    Output("portfolio-arima2", "children"),
    Input("active-portfolio-store", "data"),
)
def portfolio_mean_plus_volatility_forecast(active_portfolio_data):
    df_local = _get_current_portfolio_df(active_portfolio_data)

    if df_local.empty or "Ticker" not in df_local.columns:
        return html.Div([html.H3("Predikce - Portfolio"), html.P("V uploadovanem souboru chybi data portfolia.")])

    tickers_clean = df_local["Ticker"].astype(str).str.split(".").str[0].dropna().unique().tolist()
    prices_filtered = df_prices_all[df_prices_all["Ticker_clean"].isin(tickers_clean)].copy()
    if prices_filtered.empty:
        return html.Div([html.H3("Predikce - Portfolio"), html.P("Nenalezena cenova data pro tickery z portfolia.")])

    try:
        portfolio_hist = hodnota_portfolia_v_case(df_local, prices_filtered)
    except Exception as e:
        return html.Div([html.H3("Predikce - Portfolio"), html.P(f"Nepodarilo se sestavit historii portfolia: {e}")])

    if portfolio_hist.empty or "portfolio_value" not in portfolio_hist.columns:
        return html.Div([html.H3("Predikce - Portfolio"), html.P("Nedostatek dat pro vypocet casove rady portfolia.")])

    price_series = (
        portfolio_hist[["date", "portfolio_value"]]
        .dropna(subset=["date", "portfolio_value"])
        .drop_duplicates(subset=["date"])
        .sort_values("date")
        .set_index("date")["portfolio_value"]
        .astype(float)
    )
    price_series = price_series[price_series > 0].dropna()
    price_series = price_series.asfreq("B").ffill()

    forecast_steps = 30
    min_obs = 80
    ticker = "Portfolio"

    if len(price_series) < min_obs:
        hist = pd.DataFrame({"date": price_series.index, "adjusted_close": price_series.values})
        return html.Div([
            html.H3(f"Predikce - {ticker}"),
            html.P(f"Malo cenovych pozorovani ({len(price_series)}), minimum je {min_obs}."),
            dcc.Graph(figure=px.line(hist, x="date", y="adjusted_close", title=f"Historie ceny - {ticker}"))
        ])

    log_ret = np.log(price_series).diff().dropna()
    if len(log_ret) < min_obs:
        return html.Div([
            html.H3(f"Predikce - {ticker}"),
            html.P(f"Malo returnu ({len(log_ret)}), minimum je {min_obs}."),
        ])

    mean_model, mean_label, mean_rmse, season_period = pick_mean_model_rmse(log_ret)
    if mean_model is None:
        return html.Div([html.H3(f"Predikce - {ticker}"), html.P("Nepodarilo se najit stabilni ARIMA/SARIMA model.")])

    future_index = make_future_index(price_series.index, forecast_steps)
    future_mean_lr = pd.Series(mean_model.forecast(steps=forecast_steps).values, index=future_index, name="mu_lr")

    resid = pd.Series(getattr(mean_model, "resid", None))
    if resid is None or resid.empty:
        fitted = pd.Series(getattr(mean_model, "fittedvalues", None))
        if fitted is not None and not fitted.empty:
            aligned = log_ret.iloc[-len(fitted):]
            resid = pd.Series(aligned.values - fitted.values)
        else:
            resid = log_ret - log_ret.mean()

    sigma_future, garch_label, garch_rmse, arch_p, arch_stat = forecast_sigma_series(
        resid, future_index, forecast_steps
    )
    last_price = float(price_series.iloc[-1])
    price_pred = returns_to_price_path(last_price, future_mean_lr)
    if sigma_future.isna().all():
        hist_sigma = float(log_ret.std(ddof=1))
        sigma_future = pd.Series(np.full(forecast_steps, hist_sigma), index=future_index, name="sigma")

    lower1, upper1 = sigma_to_price_bands(last_price, future_mean_lr, sigma_future, k=1.0)
    lower2, upper2 = sigma_to_price_bands(last_price, future_mean_lr, sigma_future, k=2.0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=price_series.index, y=price_series.values, mode="lines", name=f"{ticker} - historie", line=dict(width=2, color=HISTORY_COLOR)))
    fig.add_trace(go.Scatter(x=price_pred.index, y=price_pred.values, mode="lines", name=f"{ticker} - predikce (mean)", line=dict(width=2, dash="dot", color=PREDICTION_COLOR)))
    fig.add_trace(go.Scatter(x=upper2.index, y=upper2.values, mode="lines", line=dict(width=0, color=VOLATILITY_COLOR), name="+2sigma", showlegend=False))
    fig.add_trace(go.Scatter(x=lower2.index, y=lower2.values, mode="lines", line=dict(width=0, color=VOLATILITY_COLOR), name="-2sigma", fill="tonexty", fillcolor=VOLATILITY_FILL_SOFT, showlegend=True))
    fig.add_trace(go.Scatter(x=upper1.index, y=upper1.values, mode="lines", line=dict(width=0, color=VOLATILITY_COLOR), name="+1sigma", showlegend=False))
    fig.add_trace(go.Scatter(x=lower1.index, y=lower1.values, mode="lines", line=dict(width=0, color=VOLATILITY_COLOR), name="Volatilni pasmo +/-1sigma", fill="tonexty", fillcolor=VOLATILITY_FILL_STRONG, showlegend=True))

    extra = f"{mean_label} (RMSE={mean_rmse:.4f})"
    extra += f" | ARCH p={arch_p:.4g} -> {garch_label}"
    if np.isfinite(garch_rmse):
        extra += f" (RMSE={garch_rmse:.4f})"

    fig.update_layout(
        showlegend=True,
        legend=dict(bgcolor="rgba(0,0,0,0.2)", font=dict(color="white")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#303030",
        height=550,
        margin=dict(t=50, b=40, l=40, r=40),
        title=dict(text=f"{ticker}: predikce ceny + volatilni pasmo | {extra}", y=1, x=0.5, xanchor="center", yanchor="top", font=dict(size=20, color="white", family="Arial")),
        xaxis=dict(title=dict(text="Datum", font=dict(size=16, color="white", family="Arial")), tickfont=dict(color="white", family="Arial"), showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1),
        yaxis=dict(title=dict(text="Cena", font=dict(size=16, color="white", family="Arial")), tickfont=dict(color="white", family="Arial"), showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1, rangemode="tozero"),
    )

    return html.Div([dcc.Graph(figure=fig)])
################################################x
@callback(
    Output("arima2", "children"),
    Input("ticker_pred", "value"),
)
def mean_plus_volatility_forecast(ticker):
    if ticker is None:
        return html.Div([
            html.H3("Predikce ceny + volatilní pásmo"),
            html.P("Vyberte akcii v dropdownu.")
        ])

    forecast_steps = 30
    min_obs = 80  # na kombinaci mean + vol je lepší mít víc

    # --- data pro ticker ---
    df_t = df_prices_all[df_prices_all["Ticker_clean"] == ticker].copy()
    if df_t.empty:
        return html.Div([html.P(f"Žádná data pro {ticker}.")])

    df_t["date"] = pd.to_datetime(df_t["date"], errors="coerce")
    df_t = df_t.dropna(subset=["date"]).sort_values("date")

    price_series = df_t.set_index("date")["adjusted_close"].astype(float)
    price_series = price_series.sort_index()
    price_series = price_series.asfreq("B").ffill()
    log_ret = np.log(price_series).diff().dropna()
    price_series = price_series[price_series > 0].dropna()

    if len(price_series) < min_obs:
        return html.Div([
            html.H3(f"Predikce – {ticker}"),
            html.P(f"Málo cenových pozorování ({len(price_series)}), minimum je {min_obs}."),
            dcc.Graph(figure=px.line(df_t, x="date", y="adjusted_close", title=f"Historie ceny – {ticker}"))
        ])

    # --- returny (log) ---
    log_ret = np.log(price_series).diff().dropna()

    if len(log_ret) < min_obs:
        return html.Div([
            html.H3(f"Predikce – {ticker}"),
            html.P(f"Málo returnů ({len(log_ret)}), minimum je {min_obs}."),
        ])

    # --- 1) Mean model (ARIMA nebo SARIMA) ---
    mean_model, mean_label, mean_rmse, season_period = pick_mean_model_rmse(log_ret)
    if mean_model is None:
        return html.Div([
            html.H3(f"Predikce – {ticker}"),
            html.P("Nepodařilo se najít stabilní ARIMA/SARIMA model.")
        ])

    # forecast mean returnů
    future_index = make_future_index(price_series.index, forecast_steps)
    future_mean_lr = pd.Series(mean_model.forecast(steps=forecast_steps).values, index=future_index, name="mu_lr")

    # --- 2) Rezidua mean modelu (in-sample) ---
    # Pozor: statsmodels fittedvalues má index jako u train; tady máme fit na train v grid search.
    # Pro ARCH test vezmeme rezidua z fitu, která jsou k dispozici:
    resid = pd.Series(getattr(mean_model, "resid", None))
    if resid is None or resid.empty:
        # fallback: zkusíme spočítat resid = y - fitted
        fitted = pd.Series(getattr(mean_model, "fittedvalues", None))
        if fitted is not None and not fitted.empty:
            aligned = log_ret.iloc[-len(fitted):]
            resid = aligned.values - fitted.values
            resid = pd.Series(resid)
        else:
            resid = log_ret - log_ret.mean()

    sigma_future, garch_label, garch_rmse, arch_p, arch_stat = forecast_sigma_series(
        resid, future_index, forecast_steps
    )

    # --- 5) Mean returns -> price path ---
    last_price = float(price_series.iloc[-1])
    price_pred = returns_to_price_path(last_price, future_mean_lr)

    # --- 6) Volatility band around predicted price ---
    # pokud sigma_future není k dispozici (NO-GARCH), uděláme fallback na historickou std returnů
    if sigma_future.isna().all():
        hist_sigma = float(log_ret.std(ddof=1))
        sigma_future = pd.Series(np.full(forecast_steps, hist_sigma), index=future_index, name="sigma")

    lower1, upper1 = sigma_to_price_bands(last_price, future_mean_lr, sigma_future, k=1.0)
    lower2, upper2 = sigma_to_price_bands(last_price, future_mean_lr, sigma_future, k=2.0)

    # --- 7) Jeden graf (cena + predikce + pásmo) ---
    fig = go.Figure()

    # historie ceny
    fig.add_trace(go.Scatter(
        x=price_series.index,
        y=price_series.values,
        mode="lines",
        name=f"{ticker} – historie",
        line=dict(width=2, color=HISTORY_COLOR),
    ))

    # predikce ceny
    fig.add_trace(go.Scatter(
        x=price_pred.index,
        y=price_pred.values,
        mode="lines",
        name=f"{ticker} – predikce (mean)",
        line=dict(width=2, dash="dot", color=PREDICTION_COLOR),
    ))

    # pásmo ±2σ (nejdřív)
    fig.add_trace(go.Scatter(
        x=upper2.index,
        y=upper2.values,
        mode="lines",
        line=dict(width=0, color=VOLATILITY_COLOR),
        name="+2σ",
        showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=lower2.index,
        y=lower2.values,
        mode="lines",
        line=dict(width=0, color=VOLATILITY_COLOR),
        name="-2σ",
        fill="tonexty",
        fillcolor=VOLATILITY_FILL_SOFT,
        showlegend=True,
    ))

    # pásmo ±1σ
    fig.add_trace(go.Scatter(
        x=upper1.index,
        y=upper1.values,
        mode="lines",
        line=dict(width=0, color=VOLATILITY_COLOR),
        name="+1σ",
        showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=lower1.index,
        y=lower1.values,
        mode="lines",
        line=dict(width=0, color=VOLATILITY_COLOR),
        name="Volatilní pásmo ±1σ",
        fill="tonexty",
        fillcolor=VOLATILITY_FILL_STRONG,
        showlegend=True,
    ))

    # titulky/labely
    extra = f"{mean_label} (RMSE={mean_rmse:.4f})"
    extra += f" | ARCH p={arch_p:.4g} → {garch_label}"
    if np.isfinite(garch_rmse):
        extra += f" (RMSE={garch_rmse:.4f})"

    fig.update_layout(
        showlegend=True,
        legend=dict(bgcolor="rgba(0,0,0,0.2)", font=dict(color="white")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#303030",
        height=550,
        margin=dict(t=50, b=40, l=40, r=40),
        title=dict(
            text=f"{ticker}: predikce ceny + volatilní pásmo | {extra}",
            y=1, x=0.5, xanchor="center", yanchor="top",
            font=dict(size=20, color="white", family="Arial"),
        ),
        xaxis=dict(
            title=dict(text="Datum", font=dict(size=16, color="white", family="Arial")),
            tickfont=dict(color="white", family="Arial"),
            showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1
        ),
        yaxis=dict(
            title=dict(text="Cena", font=dict(size=16, color="white", family="Arial")),
            tickfont=dict(color="white", family="Arial"),
            showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1,
            rangemode="tozero"
        ),
    )

    return html.Div([
        dcc.Graph(figure=fig)
    ])



##################################################





layout = html.Div([

    html.H1("Predikce jednotlivých aktiv a portfolia", className = "nadpis_predikce"),
    html.Div(
        className="dropdown-graph-wrapper",
        children=[
            html.H2("ARIMA predikce celeho portfolia:"),
            dcc.Loading(
                id="loading-forecast-portfolio",
                type="default",
                color="#00a17b",
                children=html.Div(id="portfolio-arima2", className="graph")
            ),
        ]
    ),

    html.Br(),
    
    
    html.Div(
        className="dropdown-graph-wrapper",
        children=[
            html.H2("ARIMA predikce cen:"),

            dcc.Dropdown(id='ticker_pred', multi=False, className="dropdown"),
            dcc.Dropdown(hodnotici_kriteria, id='kriteria_pred', multi=False,value=hodnotici_kriteria[0], className="dropdown" ),
            dcc.Loading(
                id="loading-forecast",
                type="default",
                color="#00a17b",
                children=html.Div(id="arima2", className="graph")
            ),
            
        ]
    ),



    html.Br(),

    


])
