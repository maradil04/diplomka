from dash import register_page, html, dcc, dash_table, no_update
from dash import Input, Output, State, ctx
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
from backend.services.portfolio_service import empty_transactions_dataframe, load_portfolio_transactions_dataframe, parse_money_series
from backend.session import get_current_user
from utils.portfolio_history import build_portfolio_value_history, portfolio_tickers
from utils.i18n import normalize_language, t

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
ENABLE_SARIMA = False
GARCH_CANDIDATES = tuple((p, q) for p in range(0, 3) for q in range(0, 3))


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


def _to_naive_day(series):
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None).dt.floor("D")


def _portfolio_external_flows(dataframe: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        return pd.DataFrame(columns=["Date", "flow"])

    flows = dataframe.copy()
    required = {"Date", "Type", "Total Amount"}
    if not required.issubset(set(flows.columns)):
        return pd.DataFrame(columns=["Date", "flow"])

    flows = flows[flows["Type"].isin(["CASH TOP-UP", "CASH WITHDRAWAL"])].copy()
    if flows.empty:
        return pd.DataFrame(columns=["Date", "flow"])

    flows["Date"] = _to_naive_day(flows["Date"])
    flows["flow"] = parse_money_series(flows["Total Amount"]).fillna(0.0).abs()
    flows.loc[flows["Type"].eq("CASH WITHDRAWAL"), "flow"] *= -1.0
    return flows.groupby("Date", as_index=False)["flow"].sum().sort_values("Date")


def build_portfolio_twr_index(dataframe: pd.DataFrame, price_dataframe: pd.DataFrame, base: float = 100.0) -> pd.DataFrame:
    by_day = build_portfolio_value_history(dataframe, price_dataframe)
    if by_day.empty:
        return pd.DataFrame(columns=["date", "portfolio_value", "flow", "twr_return", "twr_index"])

    out = by_day.copy()
    out["date"] = _to_naive_day(out["date"])
    out["portfolio_value"] = pd.to_numeric(out["portfolio_value"], errors="coerce").fillna(0.0)
    out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    flows = _portfolio_external_flows(dataframe)
    if not flows.empty:
        pv_dates = out[["date"]].sort_values("date")
        mapped = pd.merge_asof(
            flows,
            pv_dates,
            left_on="Date",
            right_on="date",
            direction="forward",
        ).dropna(subset=["date"])
        flow_on_pvday = mapped.groupby("date", as_index=False)["flow"].sum()
    else:
        flow_on_pvday = pd.DataFrame({"date": out["date"], "flow": 0.0})

    out = out.merge(flow_on_pvday, on="date", how="left").fillna({"flow": 0.0}).sort_values("date").reset_index(drop=True)

    first_idx = int((out["portfolio_value"] > 0).idxmax()) if (out["portfolio_value"] > 0).any() else 0
    first_value = float(out.loc[first_idx, "portfolio_value"])
    first_flow = float(out.loc[first_idx, "flow"])
    if first_value > 0:
        gap = first_value - first_flow
        if abs(gap) > max(1e-6, 1e-4 * first_value):
            out.loc[first_idx, "flow"] += gap

    values = out["portfolio_value"].astype(float).values
    flows = out["flow"].astype(float).values
    nav = np.empty_like(values, dtype=float)
    units = np.empty_like(values, dtype=float)

    nav_prev = 1.0
    units_prev = 0.0 if values[0] <= 0 else values[0] / nav_prev
    nav[0] = nav_prev
    units[0] = units_prev

    for idx in range(1, len(values)):
        if nav_prev == 0:
            nav_prev = 1.0
        units_i = units_prev + flows[idx] / nav_prev
        nav_i = 1.0 if units_i == 0 else values[idx] / units_i
        units[idx] = units_i
        nav[idx] = nav_i
        units_prev, nav_prev = units_i, nav_i

    out["twr_return"] = pd.Series(nav).pct_change().fillna(0.0)
    out["twr_index"] = base * (1.0 + out["twr_return"]).cumprod()

    pos_idx = np.argmax(units > 0)
    if units[pos_idx] > 0 and pos_idx > 0:
        out = out.iloc[pos_idx:].reset_index(drop=True)
        out["twr_index"] = base * out["twr_index"] / out["twr_index"].iloc[0]

    return out[["date", "portfolio_value", "flow", "twr_return", "twr_index"]]

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

    candidate_pairs = [(p, q) for p in p_range for q in q_range]
    for p, q in candidate_pairs:
            try:
                am = arch_model(
                    train_s,
                    mean="Zero",
                    vol="GARCH",
                    p=p,
                    q=q,
                    dist=dist,
                )
                res = am.fit(disp="off")
                horizon = len(test_s)
                fcast = res.forecast(horizon=horizon, reindex=False)
                sigma2_forecasts = np.asarray(fcast.variance.values[-1, :], dtype=float)
                if sigma2_forecasts.size != horizon:
                    sigma2_forecasts = np.resize(sigma2_forecasts, horizon)

                score = rmse((test_s.values ** 2), sigma2_forecasts)

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

    season_period = detect_seasonality_acf(log_ret, max_lag=252, threshold=0.2) if ENABLE_SARIMA else None

    best_order, best_score, _best_model, _ = grid_search_arima_rmse(
        train,
        test,
        p_range=range(0, 3),
        q_range=range(0, 3),
    )
    if best_order is None:
        return None, None, np.nan, season_period

    final_model = ARIMA(log_ret, order=best_order).fit()
    return final_model, f"ARIMA{best_order}", float(best_score), season_period


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
        p_range=sorted({pair[0] for pair in GARCH_CANDIDATES}),
        q_range=sorted({pair[1] for pair in GARCH_CANDIDATES}),
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
@app.callback(
    Output("ticker_pred", "options"),
    Output("ticker_pred", "value"),
    Input("url", "pathname"),
    Input("active-portfolio-store", "data"),
)
def update_ticker_dropdown(pathname, active_portfolio_data):
    if pathname != "/predikce":
        return no_update, no_update
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


@app.callback(
    Output("portfolio-arima2", "children"),
    Input("run-portfolio-prediction", "n_clicks"),
    Input("active-portfolio-store", "data"),
    Input("language-store", "data"),
    prevent_initial_call=True,
)
def portfolio_mean_plus_volatility_forecast(n_clicks, active_portfolio_data, language):
    lang = normalize_language(language)
    if not n_clicks:
        return html.Div([html.H3(t(lang, "pred.portfolio_header")), html.P(t(lang, "pred.click_to_run"))])
    try:
        df_local = _get_current_portfolio_df(active_portfolio_data)

        if df_local.empty or "Ticker" not in df_local.columns:
            return html.Div([html.H3(t(lang, "pred.portfolio_header")), html.P(t(lang, "pred.missing_portfolio_data"))])

        tickers_clean = df_local["Ticker"].astype(str).str.split(".").str[0].dropna().unique().tolist()
        prices_filtered = _get_portfolio_prices(df_local)
        prices_filtered = prices_filtered[prices_filtered["Ticker_clean"].isin(tickers_clean)].copy()
        if prices_filtered.empty:
            return html.Div([html.H3(t(lang, "pred.portfolio_header")), html.P(t(lang, "pred.missing_price_data"))])

        portfolio_twr = build_portfolio_twr_index(df_local, prices_filtered, base=100.0)
        if portfolio_twr.empty or "twr_index" not in portfolio_twr.columns:
            return html.Div([html.H3(t(lang, "pred.portfolio_header")), html.P(t(lang, "pred.insufficient_cf_data"))])

        performance_series = (
            portfolio_twr[["date", "twr_index"]]
            .dropna(subset=["date", "twr_index"])
            .drop_duplicates(subset=["date"])
            .sort_values("date")
            .set_index("date")["twr_index"]
            .astype(float)
        )
        performance_series = performance_series[performance_series > 0].dropna().asfreq("B").ffill()

        current_value_series = (
            portfolio_twr[["date", "portfolio_value"]]
            .dropna(subset=["date", "portfolio_value"])
            .drop_duplicates(subset=["date"])
            .sort_values("date")
            .set_index("date")["portfolio_value"]
            .astype(float)
        )
        current_value_series = current_value_series[current_value_series > 0].dropna().asfreq("B").ffill()

        forecast_steps = 30
        min_obs = 80
        ticker = "Portfolio"

        if len(performance_series) < min_obs:
            hist = pd.DataFrame({"date": performance_series.index, "adjusted_close": performance_series.values})
            return html.Div([
                html.H3(t(lang, "pred.portfolio_header")),
                html.P(t(lang, "pred.too_few_cf_obs", count=len(performance_series), minimum=min_obs)),
                dcc.Graph(figure=px.line(hist, x="date", y="adjusted_close", title=t(lang, "pred.cf_history", ticker=ticker)))
            ])

        log_ret = np.log(performance_series).diff().dropna()
        if len(log_ret) < min_obs:
            return html.Div([
                html.H3(t(lang, "pred.portfolio_header")),
                html.P(t(lang, "pred.too_few_returns", count=len(log_ret), minimum=min_obs)),
            ])

        mean_model, mean_label, mean_rmse, season_period = pick_mean_model_rmse(log_ret)
        if mean_model is None:
            return html.Div([html.H3(t(lang, "pred.portfolio_header")), html.P(t(lang, "pred.no_stable_arima"))])

        future_index = make_future_index(performance_series.index, forecast_steps)
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
        last_index_level = float(performance_series.iloc[-1])
        current_portfolio_value = float(current_value_series.iloc[-1])
        pred_index = returns_to_price_path(last_index_level, future_mean_lr)
        if sigma_future.isna().all():
            hist_sigma = float(log_ret.std(ddof=1))
            sigma_future = pd.Series(np.full(forecast_steps, hist_sigma), index=future_index, name="sigma")

        lower1_index, upper1_index = sigma_to_price_bands(last_index_level, future_mean_lr, sigma_future, k=1.0)
        lower2_index, upper2_index = sigma_to_price_bands(last_index_level, future_mean_lr, sigma_future, k=2.0)
        scale = current_portfolio_value / max(last_index_level, 1e-12)
        price_pred = pred_index * scale
        lower1, upper1 = lower1_index * scale, upper1_index * scale
        lower2, upper2 = lower2_index * scale, upper2_index * scale

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=current_value_series.index, y=current_value_series.values, mode="lines", name=t(lang, "pred.history", ticker=ticker), line=dict(width=2, color=HISTORY_COLOR)))
        fig.add_trace(go.Scatter(x=price_pred.index, y=price_pred.values, mode="lines", name=t(lang, "pred.forecast_mean", ticker=ticker), line=dict(width=2, dash="dot", color=PREDICTION_COLOR)))
        fig.add_trace(go.Scatter(x=upper2.index, y=upper2.values, mode="lines", line=dict(width=0, color=VOLATILITY_COLOR), name="+2sigma", showlegend=False))
        fig.add_trace(go.Scatter(x=lower2.index, y=lower2.values, mode="lines", line=dict(width=0, color=VOLATILITY_COLOR), name="-2sigma", fill="tonexty", fillcolor=VOLATILITY_FILL_SOFT, showlegend=True))
        fig.add_trace(go.Scatter(x=upper1.index, y=upper1.values, mode="lines", line=dict(width=0, color=VOLATILITY_COLOR), name="+1sigma", showlegend=False))
        fig.add_trace(go.Scatter(x=lower1.index, y=lower1.values, mode="lines", line=dict(width=0, color=VOLATILITY_COLOR), name=t(lang, "pred.volatility_band"), fill="tonexty", fillcolor=VOLATILITY_FILL_STRONG, showlegend=True))

        extra = f"{mean_label} on cash-flow-adjusted returns (RMSE={mean_rmse:.4f})"
        extra += f" | ARCH p={arch_p:.4g} -> {garch_label}"
        if np.isfinite(garch_rmse):
            extra += f" (RMSE={garch_rmse:.4f})"

        fig.update_layout(
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
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#303030",
            height=550,
            margin=dict(t=50, b=40, l=40, r=40),
            title=dict(text=t(lang, "pred.portfolio_chart_title", ticker=ticker, extra=extra), y=1, x=0.5, xanchor="center", yanchor="top", font=dict(size=20, color="white", family="Arial")),
            xaxis=dict(title=dict(text=t(lang, "pred.date"), font=dict(size=16, color="white", family="Arial")), tickfont=dict(color="white", family="Arial"), showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1),
            yaxis=dict(title=dict(text=t(lang, "pred.price"), font=dict(size=16, color="white", family="Arial")), tickfont=dict(color="white", family="Arial"), showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1, rangemode="tozero"),
        )

        return html.Div([dcc.Graph(figure=fig)])
    except Exception as e:
        return html.Div([
            html.H3(t(lang, "pred.portfolio_header")),
            html.P(t(lang, "pred.prediction_failed", error=str(e))),
        ])
################################################x
@app.callback(
    Output("arima2", "children"),
    Input("ticker_pred", "value"),
    Input("language-store", "data"),
)
def mean_plus_volatility_forecast(ticker, language):
    lang = normalize_language(language)
    if ticker is None:
        return html.Div([
            html.H3(t(lang, "pred.price_band_header")),
            html.P(t(lang, "pred.select_stock"))
        ])
    try:
        forecast_steps = 30
        min_obs = 80

        df_t = load_market_data(tickers=[ticker], use_cache=False).copy()
        df_t = df_t[df_t["Ticker_clean"] == ticker].copy()
        if df_t.empty:
            return html.Div([html.P(t(lang, "pred.no_data_for", ticker=ticker))])

        df_t["date"] = pd.to_datetime(df_t["date"], errors="coerce")
        df_t = df_t.dropna(subset=["date"]).sort_values("date")

        price_series = df_t.set_index("date")["adjusted_close"].astype(float)
        price_series = price_series.sort_index()
        price_series = price_series.asfreq("B").ffill()
        price_series = price_series[price_series > 0].dropna()

        if len(price_series) < min_obs:
            return html.Div([
                html.H3(f"{t(lang, 'pred.portfolio_header')} – {ticker}"),
                html.P(t(lang, "pred.too_few_price_obs", count=len(price_series), minimum=min_obs)),
                dcc.Graph(figure=px.line(df_t, x="date", y="adjusted_close", title=t(lang, "pred.price_history", ticker=ticker)))
            ])

        log_ret = np.log(price_series).diff().dropna()

        if len(log_ret) < min_obs:
            return html.Div([
                html.H3(f"{t(lang, 'pred.portfolio_header')} – {ticker}"),
                html.P(t(lang, "pred.too_few_returns", count=len(log_ret), minimum=min_obs)),
            ])

        mean_model, mean_label, mean_rmse, season_period = pick_mean_model_rmse(log_ret)
        if mean_model is None:
            return html.Div([
                html.H3(f"{t(lang, 'pred.portfolio_header')} – {ticker}"),
                html.P(t(lang, "pred.no_stable_arima"))
            ])

        future_index = make_future_index(price_series.index, forecast_steps)
        future_mean_lr = pd.Series(mean_model.forecast(steps=forecast_steps).values, index=future_index, name="mu_lr")

        resid = pd.Series(getattr(mean_model, "resid", None))
        if resid is None or resid.empty:
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

        last_price = float(price_series.iloc[-1])
        price_pred = returns_to_price_path(last_price, future_mean_lr)

        if sigma_future.isna().all():
            hist_sigma = float(log_ret.std(ddof=1))
            sigma_future = pd.Series(np.full(forecast_steps, hist_sigma), index=future_index, name="sigma")

        lower1, upper1 = sigma_to_price_bands(last_price, future_mean_lr, sigma_future, k=1.0)
        lower2, upper2 = sigma_to_price_bands(last_price, future_mean_lr, sigma_future, k=2.0)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=price_series.index,
            y=price_series.values,
            mode="lines",
            name=t(lang, "pred.history", ticker=ticker),
            line=dict(width=2, color=HISTORY_COLOR),
        ))
        fig.add_trace(go.Scatter(
            x=price_pred.index,
            y=price_pred.values,
            mode="lines",
            name=t(lang, "pred.forecast_mean", ticker=ticker),
            line=dict(width=2, dash="dot", color=PREDICTION_COLOR),
        ))
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
            name=t(lang, "pred.volatility_band"),
            fill="tonexty",
            fillcolor=VOLATILITY_FILL_STRONG,
            showlegend=True,
        ))

        extra = f"{mean_label} (RMSE={mean_rmse:.4f})"
        extra += f" | ARCH p={arch_p:.4g} → {garch_label}"
        if np.isfinite(garch_rmse):
            extra += f" (RMSE={garch_rmse:.4f})"

        fig.update_layout(
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
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#303030",
            height=550,
            margin=dict(t=50, b=40, l=40, r=40),
            title=dict(
                text=t(lang, "pred.price_chart_title", ticker=ticker, extra=extra),
                y=1, x=0.5, xanchor="center", yanchor="top",
                font=dict(size=20, color="white", family="Arial"),
            ),
            xaxis=dict(
                title=dict(text=t(lang, "pred.date"), font=dict(size=16, color="white", family="Arial")),
                tickfont=dict(color="white", family="Arial"),
                showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1
            ),
            yaxis=dict(
                title=dict(text=t(lang, "pred.price"), font=dict(size=16, color="white", family="Arial")),
                tickfont=dict(color="white", family="Arial"),
                showgrid=True, gridcolor="rgba(255,255,255,0.1)", gridwidth=1,
                rangemode="tozero"
            ),
        )

        return html.Div([
            dcc.Graph(figure=fig)
        ])
    except Exception as e:
        return html.Div([
            html.H3(f"{t(lang, 'pred.portfolio_header')} – {ticker}"),
            html.P(t(lang, "pred.prediction_failed", error=str(e))),
        ])



##################################################





@app.callback(
    Output("pred-page-title", "children"),
    Output("pred-portfolio-title", "children"),
    Output("run-portfolio-prediction", "children"),
    Output("pred-portfolio-placeholder-title", "children"),
    Output("pred-portfolio-placeholder-text", "children"),
    Output("pred-asset-title", "children"),
    Input("language-store", "data"),
)
def localize_prediction_static_text(language):
    lang = normalize_language(language)
    return (
        t(lang, "pred.page_title"),
        t(lang, "pred.portfolio_title"),
        t(lang, "pred.run_portfolio"),
        t(lang, "pred.portfolio_header"),
        t(lang, "pred.click_to_run"),
        t(lang, "pred.asset_title"),
    )


layout = html.Div([

    html.H1("Predikce jednotlivých aktiv a portfolia", id="pred-page-title", className = "nadpis_predikce"),
    html.Div(
        className="dropdown-graph-wrapper",
        children=[
            html.H2("ARIMA predikce celeho portfolia:", id="pred-portfolio-title"),
            html.Div(
                style={"display": "flex", "justifyContent": "center", "marginBottom": "16px"},
                children=[
                    html.Button(
                        "Spustit predikci portfolia",
                        id="run-portfolio-prediction",
                        n_clicks=0,
                        className="rb-btn rb-pill",
                        style={"width": "min(320px, 100%)"},
                    )
                ],
            ),
            dcc.Loading(
                id="loading-forecast-portfolio",
                type="default",
                color="#00a17b",
                children=html.Div(
                    id="portfolio-arima2",
                    className="graph",
                    children=html.Div(
                        [
                            html.H3("Predikce - Portfolio", id="pred-portfolio-placeholder-title"),
                            html.P("Kliknete na tlacitko pro spusteni predikce aktivniho portfolia.", id="pred-portfolio-placeholder-text"),
                        ]
                    ),
                )
            ),
        ]
    ),

    html.Br(),
    
    
    html.Div(
        className="dropdown-graph-wrapper",
        children=[
            html.H2("ARIMA predikce cen:", id="pred-asset-title"),

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
