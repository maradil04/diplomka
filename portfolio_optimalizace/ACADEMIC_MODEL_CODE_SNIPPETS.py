"""
Full computational implementations extracted from:
- pages/predikce.py
- pages/rebalance.py

Dash callbacks and presentation-only code are intentionally excluded.
The statistical tests, model-selection logic, optimization objectives,
constraints, fallbacks, and numerical-stability handling are preserved.
"""

import numpy as np
import pandas as pd
from arch import arch_model
from scipy.optimize import linprog, minimize
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller


ENABLE_SARIMA = False
GARCH_CANDIDATES = [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (1, 3)]


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


def log_returns_from_prices(price_series: pd.Series) -> pd.Series:
    """log(P_t) - log(P_{t-1})"""
    s = pd.Series(price_series).astype(float)
    return np.log(s + 1e-12).diff().dropna()


def estimate_d_min_adf(series: pd.Series, max_d: int = 2, alpha: float = 0.05) -> int:
    """
    Find the smallest d (0..max_d) for which ADF rejects the unit root
    hypothesis (p < alpha).
    """
    x = pd.Series(series).dropna().astype(float)
    if len(x) < 30:
        return 0

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

    # Fallback best model without the residual-whiteness requirement.
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
                    is_white, p_lb = ljung_box_test(
                        resid,
                        lags=lb_lags,
                        alpha=lb_alpha,
                    )

                    results.append(
                        {
                            "order": order,
                            "rmse": float(score),
                            "ljung_box_ok": bool(is_white),
                            "ljung_box_pvalue": p_lb,
                        }
                    )

                    if np.isfinite(score) and score < best_rmse_any:
                        best_rmse_any = score
                        best_order_any = order

                    if np.isfinite(score) and score < best_rmse and is_white:
                        best_rmse = score
                        best_order = order

                except Exception as e:
                    results.append(
                        {
                            "order": order,
                            "rmse": np.nan,
                            "ljung_box_ok": None,
                            "ljung_box_pvalue": np.nan,
                            "error": str(e),
                        }
                    )

    results_df = pd.DataFrame(results)
    if "rmse" in results_df.columns:
        results_df = results_df.sort_values("rmse", na_position="last")

    if best_order is None:
        best_order, best_rmse = best_order_any, float(best_rmse_any)

    return best_order, float(best_rmse), None, results_df


def pick_mean_model_rmse(log_ret: pd.Series):
    train, test = train_test_split_series(log_ret, test_size=0.2)

    best_order, best_score, _best_model, results = grid_search_arima_rmse(
        train,
        test,
        p_range=range(0, 3),
        q_range=range(0, 3),
    )
    if best_order is None:
        return None, None, np.nan, results

    final_model = ARIMA(log_ret, order=best_order).fit()
    return final_model, f"ARIMA{best_order}", float(best_score), results


def detect_arch_effect(residuals: pd.Series, alpha: float = 0.05, lags: int = 12):
    """
    Engle ARCH LM test on model residuals.
    Returns (has_arch, pvalue, statistic).
    """
    r = pd.Series(residuals).dropna().astype(float)
    if len(r) < max(50, lags * 5):
        return False, np.nan, np.nan

    stat, pvalue, _, _ = het_arch(r, nlags=lags)
    return (pvalue < alpha), float(pvalue), float(stat)


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

    # Percentage scaling improves optimization stability for daily returns.
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
            sigma2_forecasts = np.asarray(
                fcast.variance.values[-1, :],
                dtype=float,
            )
            if sigma2_forecasts.size != horizon:
                sigma2_forecasts = np.resize(sigma2_forecasts, horizon)

            score = rmse((test_s.values**2), sigma2_forecasts)
            results.append({"p": p, "q": q, "rmse": score})

            if np.isfinite(score) and score < best_score:
                best_score = score
                best_order = (p, q)

        except Exception as e:
            results.append(
                {"p": p, "q": q, "rmse": np.nan, "error": str(e)}
            )

    results_df = pd.DataFrame(results)
    if "rmse" in results_df.columns:
        results_df = results_df.sort_values("rmse", na_position="last")

    return best_order, best_score, None, results_df


def forecast_sigma_series(
    residuals: pd.Series,
    future_index: pd.DatetimeIndex,
    forecast_steps: int,
):
    sigma_future = pd.Series(
        np.full(forecast_steps, np.nan),
        index=future_index,
        name="sigma",
    )
    garch_label = "NO-GARCH"
    garch_rmse = np.nan

    has_arch, arch_p, arch_stat = detect_arch_effect(
        residuals,
        alpha=0.05,
        lags=12,
    )
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
    am = arch_model(
        scaled_resid,
        mean="Zero",
        vol="GARCH",
        p=p_opt,
        q=q_opt,
        dist="normal",
    )
    res = am.fit(disp="off")
    fcast = res.forecast(horizon=forecast_steps, reindex=False)
    sigma2 = fcast.variance.values[-1, :]
    sigma_future = pd.Series(
        np.sqrt(sigma2) / 100.0,
        index=future_index,
        name="sigma",
    )
    return sigma_future, garch_label, garch_rmse, arch_p, arch_stat


def prices_to_returns(df_prices: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize market prices into a wide daily returns dataframe.
    Supports both long and wide input, and prefers adjusted_close when available.
    """
    dfp = df_prices.copy()

    date_col = next(
        (c for c in ["Date", "date", "DATUM", "datum"] if c in dfp.columns),
        None,
    )
    if date_col is None:
        raise ValueError("df_prices must contain a Date/date column.")

    dfp[date_col] = pd.to_datetime(dfp[date_col], errors="coerce")
    dfp = dfp.dropna(subset=[date_col])

    has_ticker = any(str(c).lower() == "ticker" for c in dfp.columns)
    if has_ticker:
        ticker_col = next(c for c in dfp.columns if str(c).lower() == "ticker")
        price_col = next(
            (
                c
                for c in [
                    "adjusted_close",
                    "Adj Close",
                    "adj_close",
                    "Close",
                    "close",
                    "Price",
                    "price",
                ]
                if c in dfp.columns
            ),
            None,
        )
        if price_col is None:
            raise ValueError(
                "Long df_prices must contain adjusted_close, Close, "
                "Adj Close, or Price."
            )

        wide_prices = (
            dfp.sort_values([date_col, ticker_col])
            .pivot(index=date_col, columns=ticker_col, values=price_col)
        )
    else:
        cols = [c for c in dfp.columns if c != date_col]
        if not cols:
            raise ValueError("Wide df_prices contains no ticker columns.")
        wide_prices = dfp.sort_values(date_col).set_index(date_col)[cols]

    rets = wide_prices.pct_change().dropna(how="all")
    rets = rets.dropna(axis=1, thresh=max(5, int(0.7 * len(rets))))
    rets = rets.dropna()
    return rets


def mean_variance_optimize(mu, Sigma, lam=5.0, long_only=True):
    """
    mu: (n,) expected returns
    Sigma: (n,n) covariance matrix
    lam: risk-aversion coefficient
    """
    n = len(mu)

    def objective(w):
        ret = np.dot(mu, w)
        risk = np.dot(w, Sigma @ w)
        return -(ret - lam * risk)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    if long_only:
        bounds = [(0.0, 1.0) for _ in range(n)]
    else:
        bounds = [(-1.0, 1.0) for _ in range(n)]

    w0 = np.ones(n) / n

    res = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not res.success:
        raise ValueError(f"Optimization failed: {res.message}")

    return res.x


def prepare_and_run_mean_variance(
    returns: pd.DataFrame,
    lam=5.0,
    long_only=True,
):
    ann_factor = 252
    mu = returns.mean().values * ann_factor
    Sigma = returns.cov().values * ann_factor

    eps = 1e-8
    Sigma = Sigma + eps * np.eye(Sigma.shape[0])

    weights = mean_variance_optimize(
        mu,
        Sigma,
        lam=float(lam),
        long_only=long_only,
    )

    expected_return = float(mu @ weights)
    variance = float(weights @ (Sigma @ weights))
    volatility = float(np.sqrt(max(variance, 0.0)))

    return weights, expected_return, variance, volatility


def risk_parity_erc(Sigma, long_only=True, gross_cap=1.0):
    """Find Equal Risk Contribution risk-parity weights."""
    n = Sigma.shape[0]

    def risk_contrib(w):
        vol = np.sqrt(max(w @ (Sigma @ w), 1e-18))
        marginal_risk = Sigma @ w
        contributions = (w * marginal_risk) / vol
        return contributions, vol

    def objective(w):
        contributions, _ = risk_contrib(w)
        target = np.mean(contributions)
        return np.sum((contributions - target) ** 2)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    constraints.append(
        {
            "type": "ineq",
            "fun": lambda w: gross_cap - np.sum(np.abs(w)),
        }
    )

    if long_only:
        bounds = [(0.0, 1.0) for _ in range(n)]
    else:
        bounds = [(-1.0, 1.0) for _ in range(n)]

    w0 = np.ones(n) / n
    res = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not res.success:
        raise ValueError(f"Risk parity failed: {res.message}")

    return res.x


def prepare_and_run_risk_parity(
    returns: pd.DataFrame,
    long_only=True,
    gross_cap=1.0,
):
    Sigma = returns.cov().values * 252
    Sigma = Sigma + 1e-8 * np.eye(Sigma.shape[0])

    weights = risk_parity_erc(
        Sigma,
        long_only=long_only,
        gross_cap=float(gross_cap),
    )

    volatility = float(np.sqrt(max(weights @ (Sigma @ weights), 0.0)))
    marginal_risk = Sigma @ weights
    risk_contributions = (
        weights * marginal_risk
    ) / max(volatility, 1e-12)

    return weights, volatility, risk_contributions


def cvar_optimize(
    returns: np.ndarray,
    alpha: float = 0.95,
    long_only: bool = True,
):
    """
    Minimize CVaR (Expected Shortfall) of losses at confidence level alpha.

    Variables:
        w: asset weights
        t: VaR
        u: scenario-specific slack variables
    """
    T, N = returns.shape
    a = float(alpha)

    # Objective variables are [w(0..N-1), t, u(0..T-1)].
    c = np.zeros(N + 1 + T)
    c[N] = 1.0
    c[N + 1 :] = 1.0 / ((1.0 - a) * T)

    # loss_i - t <= u_i, where loss_i = -(r_i dot w).
    A_ub = np.zeros((T, N + 1 + T))
    b_ub = np.zeros(T)
    A_ub[:, :N] = -returns
    A_ub[:, N] = -1.0
    A_ub[np.arange(T), N + 1 + np.arange(T)] = -1.0

    # u_i >= 0.
    A_ub2 = np.zeros((T, N + 1 + T))
    b_ub2 = np.zeros(T)
    A_ub2[np.arange(T), N + 1 + np.arange(T)] = -1.0

    A_ub = np.vstack([A_ub, A_ub2])
    b_ub = np.concatenate([b_ub, b_ub2])

    # Fully invested portfolio: sum(w) = 1.
    A_eq = np.zeros((1, N + 1 + T))
    A_eq[0, :N] = 1.0
    b_eq = np.array([1.0])

    bounds = []
    if long_only:
        bounds += [(0.0, 1.0)] * N
    else:
        bounds += [(-1.0, 1.0)] * N
    bounds.append((None, None))
    bounds += [(0.0, None)] * T

    res = linprog(
        c,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not res.success:
        raise ValueError(res.message)

    weights = res.x[:N]
    value_at_risk = res.x[N]
    slack = res.x[N + 1 :]
    cvar = value_at_risk + (
        1.0 / ((1.0 - a) * T)
    ) * np.sum(slack)
    return weights, float(value_at_risk), float(cvar)


def prepare_and_run_cvar(
    returns: pd.DataFrame,
    alpha=0.95,
    long_only=True,
):
    return cvar_optimize(
        returns.values,
        alpha=float(alpha),
        long_only=long_only,
    )
