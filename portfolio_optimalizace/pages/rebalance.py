from dash import register_page, html, dcc, dash_table, Input, Output, State, callback, no_update
import pandas as pd
import numpy as np
from scipy.optimize import minimize

from backend.services.market_data_service import load_market_data
from backend.services.portfolio_service import empty_transactions_dataframe, load_portfolio_transactions_dataframe
from backend.services.rebalance_portfolio_service import create_rebalance_portfolio
from backend.services.portfolio_service import list_user_portfolios
from backend.session import get_current_user

register_page(__name__, path="/rebalance")

df_empty = empty_transactions_dataframe()
df_prices = load_market_data().copy()
df_prices_all = load_market_data().copy()
df_prices["Ticker_clean"] = df_prices["Ticker"].str.split(".").str[0]
df_prices_all = df_prices.copy()

def _get_current_portfolio_df(active_portfolio_data):
    user = get_current_user()
    portfolio_id = (active_portfolio_data or {}).get("portfolio_id") if isinstance(active_portfolio_data, dict) else None
    if user and portfolio_id:
        loaded = load_portfolio_transactions_dataframe(user["id"], portfolio_id, fallback=df_empty)
        return loaded.copy() if isinstance(loaded, pd.DataFrame) else df_empty.copy()
    return df_empty.copy()


def _get_portfolio_prices(active_portfolio_data):
    tickers = _portfolio_tickers_from_active_portfolio(active_portfolio_data)
    if tickers:
        return load_market_data(tickers=tickers, use_cache=False).copy()
    return load_market_data(use_cache=False).copy()


def _portfolio_tickers_from_active_portfolio(active_portfolio_data):
    df_local = _get_current_portfolio_df(active_portfolio_data)
    if "Ticker" not in df_local.columns:
        return set()
    return set(df_local["Ticker"].dropna().astype(str))

def _table_to_tsv(rows, columns):
    if not rows:
        return ""
    headers = [c["name"] if isinstance(c, dict) else str(c) for c in columns]
    ids = [c["id"] if isinstance(c, dict) else str(c) for c in columns]
    lines = ["\t".join(headers)]
    for r in rows:
        line = []
        for cid in ids:
            v = r.get(cid, "")
            line.append("" if v is None else str(v))
        lines.append("\t".join(line))
    return "\n".join(lines)

def prices_to_returns(df_prices: pd.DataFrame) -> pd.DataFrame:
    """
    Vrátí wide returns DF: index=Date, columns=Tickers, values=daily returns.
    Podporuje:
      - wide: sloupec Date + tickery jako sloupce
      - long: sloupce Date + Ticker (+ Close/Adj Close/Price)
    """
    dfp = df_prices.copy()

    # 1) najdi date column
    date_col = None
    for c in ["Date", "date", "DATUM", "datum"]:
        if c in dfp.columns:
            date_col = c
            break

    if date_col is None:
        raise ValueError("df_prices nemá sloupec Date/date.")

    dfp[date_col] = pd.to_datetime(dfp[date_col])

    # 2) detekce long vs wide
    has_ticker = any(c.lower() == "ticker" for c in dfp.columns)
    if has_ticker:
        # long format
        ticker_col = [c for c in dfp.columns if c.lower() == "ticker"][0]

        price_col = None
        for c in ["Adj Close", "adj_close", "Close", "close", "Price", "price"]:
            if c in dfp.columns:
                price_col = c
                break
        if price_col is None:
            raise ValueError("Long df_prices musí mít Close/Adj Close/Price.")

        wide_prices = (
            dfp
            .sort_values([date_col, ticker_col])
            .pivot(index=date_col, columns=ticker_col, values=price_col)
        )
    else:
        # wide format: date + ostatní sloupce tickery
        cols = [c for c in dfp.columns if c != date_col]
        if len(cols) == 0:
            raise ValueError("Wide df_prices nemá žádné ticker sloupce.")
        wide_prices = dfp.sort_values(date_col).set_index(date_col)[cols]

    # 3) returns
    rets = wide_prices.pct_change().dropna(how="all")

    # vyhoď tickery s moc NA
    rets = rets.dropna(axis=1, thresh=max(5, int(0.7 * len(rets))))  # aspoň 70% dat
    rets = rets.dropna()

    return rets

def mean_variance_optimize(mu, Sigma, lam=5.0, long_only=True):
    """
    mu: (n,) expected returns
    Sigma: (n,n) covariance matrix
    lam: risk aversion λ
    """
    n = len(mu)

    # cíl: minimalizace záporné utility
    def objective(w):
        ret = np.dot(mu, w)
        risk = np.dot(w, Sigma @ w)
        return -(ret - lam * risk)

    # constraint: sum(w)=1
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    # bounds
    if long_only:
        bounds = [(0.0, 1.0) for _ in range(n)]
    else:
        bounds = [(-1.0, 1.0) for _ in range(n)]  # nebo None

    w0 = np.ones(n) / n

    res = minimize(objective, w0, method="SLSQP", bounds=bounds, constraints=constraints)

    if not res.success:
        raise ValueError(f"Optimization failed: {res.message}")

    return res.x



def risk_parity_erc(Sigma, long_only=True, gross_cap=1.0):
    """
    Najde ERC risk parity weights.
    - long_only: w>=0 (doporučeno)
    - gross_cap: Σ|w| (pro long-only je to 1.0; když povolíš short, nastav třeba 1.5–2.0)
    """
    n = Sigma.shape[0]

    def risk_contrib(w):
        # portfolio volatility
        vol = np.sqrt(max(w @ (Sigma @ w), 1e-18))
        m = Sigma @ w
        rc = (w * m) / vol
        return rc, vol

    # cíl: risk contributions co nejvíc stejné
    def objective(w):
        rc, _ = risk_contrib(w)
        target = np.mean(rc)
        return np.sum((rc - target) ** 2)

    # constraint: net exposure = 1
    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    # gross cap (funguje i pro long-only; pro long-only je to redundantní, ale nevadí)
    cons.append({"type": "ineq", "fun": lambda w: gross_cap - np.sum(np.abs(w))})

    if long_only:
        bounds = [(0.0, 1.0) for _ in range(n)]
    else:
        bounds = [(-1.0, 1.0) for _ in range(n)]

    w0 = np.ones(n) / n
    res = minimize(objective, w0, method="SLSQP", bounds=bounds, constraints=cons)

    if not res.success:
        raise ValueError(f"Risk parity failed: {res.message}")

    return res.x




from scipy.optimize import linprog

def cvar_optimize(returns: np.ndarray, alpha: float = 0.95, long_only: bool = True):
    """
    Minimizuje CVaR (Expected Shortfall) ztrát na hladině alpha.
    returns: (T, N) matice výnosů (scénáře = řádky, aktiva = sloupce)
    proměnné: w (N), t (1) = VaR, u (T) slack
    min t + (1/((1-a)T))*sum u
    s.t. u_i >= 0
         u_i >= loss_i - t, kde loss_i = -(r_i · w)
         sum(w)=1
    """
    T, N = returns.shape
    a = float(alpha)

    # objective vector c for [w(0..N-1), t, u(0..T-1)]
    c = np.zeros(N + 1 + T)
    c[N] = 1.0  # t
    c[N+1:] = 1.0 / ((1.0 - a) * T)

    # Inequalities A_ub x <= b_ub
    # u_i >= loss_i - t  =>  -u_i - t - (r_i·w) <= 0  ??? let's derive carefully:
    # loss_i - t <= u_i
    # -(r_i·w) - t - u_i <= 0
    A_ub = np.zeros((T, N + 1 + T))
    b_ub = np.zeros(T)
    A_ub[:, :N] = -returns          # -(r_i·w)
    A_ub[:, N] = -1.0               # -t
    A_ub[np.arange(T), N+1+np.arange(T)] = -1.0  # -u_i

    # u_i >= 0  =>  -u_i <= 0
    A_ub2 = np.zeros((T, N + 1 + T))
    b_ub2 = np.zeros(T)
    A_ub2[np.arange(T), N+1+np.arange(T)] = -1.0

    A_ub = np.vstack([A_ub, A_ub2])
    b_ub = np.concatenate([b_ub, b_ub2])

    # Equality: sum(w)=1
    A_eq = np.zeros((1, N + 1 + T))
    A_eq[0, :N] = 1.0
    b_eq = np.array([1.0])

    # bounds
    bounds = []
    if long_only:
        bounds += [(0.0, 1.0)] * N
    else:
        bounds += [(-1.0, 1.0)] * N  # případně zpřísni
    bounds.append((None, None))      # t (VaR)
    bounds += [(0.0, None)] * T      # u_i

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
        raise ValueError(res.message)

    w = res.x[:N]
    t = res.x[N]
    u = res.x[N+1:]
    cvar = t + (1.0 / ((1.0 - a) * T)) * np.sum(u)
    return w, float(t), float(cvar)


















































###############################################################################



################################################################################


###############################################################################xx

@callback(
    Output("mv-table", "data"),
    Output("mv-status", "children"),
    Input("mv-run", "n_clicks"),
    State("active-portfolio-store", "data"),
    State("mv-lambda", "value"),
    State("mv-longonly", "value"),
    prevent_initial_call=True
)
def run_rebalance(n_clicks, active_portfolio_data, lam, longonly_values):
    long_only = "LONG" in (longonly_values or [])

    # 1) Získej returns
    try:
        prices = _get_portfolio_prices(active_portfolio_data)
        rets = prices_to_returns(prices)
        source = "database-backed market prices for active portfolio"
    except Exception as e:
        return [], html.Div(f"Nepodařilo se připravit returns: {e}", style={"color": "crimson"})

    rets = rets.dropna(how="all").dropna(axis=1, how="all")

    if rets.shape[1] < 2 or len(rets) < 10:
        return [], html.Div("Potřebuji alespoň 2 aktiva a dostatek pozorování (>=10).", style={"color": "crimson"})

    # 2) (Volitelné) omez na tickery z portfolia
    try:
        portfolio_tickers = _portfolio_tickers_from_active_portfolio(active_portfolio_data)
        if len(portfolio_tickers) < 2:
            return [], html.Div("The active portfolio needs at least 2 tickers for rebalance.", style={"color": "crimson"})
        common = [t for t in rets.columns if t in portfolio_tickers]
        if len(common) >= 2:
            rets = rets[common]
    except Exception:
        pass

    tickers_local = list(rets.columns)

    # 3) Spočti mu a Sigma (ANUALIZACE)
    # Pokud máš jiné frekvence dat, uprav 252 na 12 (měsíční) / 365 (krypto) apod.
    ann_factor = 252
    mu = rets.mean().values * ann_factor
    Sigma = rets.cov().values * ann_factor

    # numerická stabilizace (jitter na diagonálu)
    eps = 1e-8
    Sigma = Sigma + eps * np.eye(Sigma.shape[0])

    # 4) Optimalizuj
    try:
        w = mean_variance_optimize(mu, Sigma, lam=float(lam), long_only=long_only)
    except Exception as e:
        return [], html.Div(f"Optimalizace selhala: {e}", style={"color": "crimson"})

    # 5) Výstup
    out = [{"ticker": t, "weight": float(wi)} for t, wi in zip(tickers_local, w)]

    # 6) Metriky portfolia (pro status)
    net = float(np.sum(w))
    gross = float(np.sum(np.abs(w)))

    exp_ret = float(mu @ w)                 # anualizovaný E[R]
    var = float(w @ (Sigma @ w))            # anualizovaná variance
    vol = float(np.sqrt(max(var, 0.0)))     # anualizovaná volatilita

    status = html.Div([
        html.Div(f"Zdroj dat: {source}"),
        html.Div(f"E[R] (annual) = {exp_ret:.4%}"),
        html.Div(f"Vol (annual) = {vol:.4%}  |  Var (annual) = {var:.6g}"),
        html.Div(f"Gross exposure Σ|w| = {gross:.6f}  |  Net exposure Σw = {net:.6f}"),
        html.Div(f"λ = {lam}, long-only = {long_only}, assets = {len(tickers_local)}"),
    ], style={"color": "seagreen", "textAlign": "center"})

    return out, status




@callback(
    Output("rp-table", "data"),
    Output("rp-status", "children"),
    Input("rp-run", "n_clicks"),
    State("active-portfolio-store", "data"),
    State("rp-longonly", "value"),
    State("rp-gross-cap", "value"),
    prevent_initial_call=True
)
def run_risk_parity(n_clicks, active_portfolio_data, longonly_values, gross_cap):
    long_only = "LONG" in (longonly_values or [])

    # returns
    try:
        prices = _get_portfolio_prices(active_portfolio_data)
        rets = prices_to_returns(prices)
        source = "database-backed market prices for active portfolio"
    except Exception as e:
        return [], html.Div(f"Nepodařilo se připravit returns: {e}", style={"color": "crimson"})

    rets = rets.dropna(how="all").dropna(axis=1, how="all").dropna()

    if rets.shape[1] < 2 or len(rets) < 10:
        return [], html.Div("Potřebuji alespoň 2 aktiva a dostatek pozorování (>=10).",
                            style={"color": "crimson"})

    # portfolio tickers only (volitelné)
    try:
        portfolio_tickers = _portfolio_tickers_from_active_portfolio(active_portfolio_data)
        if len(portfolio_tickers) < 2:
            return [], html.Div("The active portfolio needs at least 2 tickers for rebalance.", style={"color": "crimson"})
        common = [t for t in rets.columns if t in portfolio_tickers]
        if len(common) >= 2:
            rets = rets[common]
    except Exception:
        pass

    tickers_local = list(rets.columns)

    # covariance (annualized for reporting)
    ann = 252
    Sigma = rets.cov().values * ann
    Sigma = Sigma + 1e-8 * np.eye(Sigma.shape[0])

    try:
        w = risk_parity_erc(Sigma, long_only=long_only, gross_cap=float(gross_cap))
    except Exception as e:
        return [], html.Div(f"Risk parity selhala: {e}", style={"color": "crimson"})

    # risk contributions
    vol = float(np.sqrt(max(w @ (Sigma @ w), 0.0)))
    m = Sigma @ w
    rc = (w * m) / max(vol, 1e-12)   # contribution to vol

    out = [
        {"ticker": t, "weight": float(wi), "rc": float(rci)}
        for t, wi, rci in zip(tickers_local, w, rc)
    ]

    status = html.Div([
        html.Div(f"Zdroj dat: {source}"),
        html.Div(f"Vol (annual) = {vol:.4%}"),
        html.Div(f"Gross Σ|w| = {float(np.sum(np.abs(w))):.6f} | Net Σw = {float(np.sum(w)):.6f}"),
        html.Div(f"Long-only = {long_only}, assets = {len(tickers_local)}"),
    ], style={"color": "seagreen", "textAlign": "center"})

    return out, status



@callback(
    Output("cvar-table", "data"),
    Output("cvar-status", "children"),
    Input("cvar-run", "n_clicks"),
    State("active-portfolio-store", "data"),
    State("cvar-alpha", "value"),
    State("cvar-longonly", "value"),
    prevent_initial_call=True
)
def run_cvar(n_clicks, active_portfolio_data, alpha, longonly_values):
    long_only = "LONG" in (longonly_values or [])

    # returns
    try:
        prices = _get_portfolio_prices(active_portfolio_data)
        rets = prices_to_returns(prices)
        source = "database-backed market prices for active portfolio"
    except Exception as e:
        return [], html.Div(f"Nepodařilo se připravit returns: {e}", style={"color": "crimson"})

    rets = rets.dropna(how="all").dropna(axis=1, how="all").dropna()

    if rets.shape[1] < 2 or len(rets) < 30:
        return [], html.Div("Potřebuji alespoň 2 aktiva a dostatek scénářů (>=30).",
                            style={"color": "crimson"})

    # omez na tickery v portfoliu (volitelné)
    try:
        portfolio_tickers = _portfolio_tickers_from_active_portfolio(active_portfolio_data)
        if len(portfolio_tickers) < 2:
            return [], html.Div("The active portfolio needs at least 2 tickers for rebalance.", style={"color": "crimson"})
        common = [t for t in rets.columns if t in portfolio_tickers]
        if len(common) >= 2:
            rets = rets[common]
    except Exception:
        pass

    tickers_local = list(rets.columns)

    # CVaR optimalizace na denních scénářích
    R = rets.values  # (T, N)

    try:
        w, var_t, cvar = cvar_optimize(R, alpha=float(alpha), long_only=long_only)
    except Exception as e:
        return [], html.Div(f"CVaR optimalizace selhala: {e}", style={"color": "crimson"})

    out = [{"ticker": t, "weight": float(wi)} for t, wi in zip(tickers_local, w)]

    # reporting: CVaR je na ztrátách (loss). Zde je to "expected loss" při nejhorších (1-alpha) scénářích.
    # Volitelně hrubá expozice:
    gross = float(np.sum(np.abs(w)))
    net = float(np.sum(w))

    status = html.Div([
        html.Div(f"Zdroj dat: {source}"),
        html.Div(f"α = {float(alpha):.2f}, long-only = {long_only}, assets = {len(tickers_local)}"),
        html.Div(f"VaR (loss) ≈ {var_t:.4%} | CVaR/ES (loss) ≈ {cvar:.4%}  (na periodu dat)"),
        html.Div(f"Gross Σ|w| = {gross:.6f} | Net Σw = {net:.6f}"),
    ], style={"color": "seagreen", "textAlign": "center"})

    return out, status

@callback(
    Output("mv-clip", "content"),
    Input("mv-table", "data"),
)
def set_mv_clipboard(rows):
    cols = [
        {"name": "Ticker", "id": "ticker"},
        {"name": "Weight", "id": "weight"},
    ]
    return _table_to_tsv(rows or [], cols)

@callback(
    Output("rp-clip", "content"),
    Input("rp-table", "data"),
)
def set_rp_clipboard(rows):
    cols = [
        {"name": "Ticker", "id": "ticker"},
        {"name": "Weight", "id": "weight"},
        {"name": "Risk contrib", "id": "rc"},
    ]
    return _table_to_tsv(rows or [], cols)

@callback(
    Output("cvar-clip", "content"),
    Input("cvar-table", "data"),
)
def set_cvar_clipboard(rows):
    cols = [
        {"name": "Ticker", "id": "ticker"},
        {"name": "Weight", "id": "weight"},
    ]
    return _table_to_tsv(rows or [], cols)


def _save_rebalance_result(active_portfolio_data, portfolio_name, rows, derived_from):
    user = get_current_user()
    if not user:
        return no_update, no_update, no_update

    source_portfolio_id = (active_portfolio_data or {}).get("portfolio_id") if isinstance(active_portfolio_data, dict) else None
    if not source_portfolio_id:
        return "Select a source portfolio first.", no_update, no_update

    try:
        portfolio, _simulated_df = create_rebalance_portfolio(
            user_id=user["id"],
            source_portfolio_id=source_portfolio_id,
            portfolio_name=portfolio_name,
            rebalance_rows=rows or [],
            derived_from=derived_from,
        )
        portfolios = list_user_portfolios(user["id"])
        return f"Saved portfolio: {portfolio['name']}", portfolios, ""
    except Exception as exc:
        return f"Save failed: {exc}", no_update, no_update


@callback(
    Output("mv-save-status", "children"),
    Output("portfolio-list-store", "data", allow_duplicate=True),
    Output("mv-save-name", "value"),
    Input("mv-save-button", "n_clicks"),
    State("active-portfolio-store", "data"),
    State("mv-save-name", "value"),
    State("mv-table", "data"),
    prevent_initial_call=True,
)
def save_mv_portfolio(n_clicks, active_portfolio_data, portfolio_name, rows):
    if not n_clicks:
        return no_update, no_update, no_update
    return _save_rebalance_result(active_portfolio_data, portfolio_name, rows, "rebalance_mv")


@callback(
    Output("rp-save-status", "children"),
    Output("portfolio-list-store", "data", allow_duplicate=True),
    Output("rp-save-name", "value"),
    Input("rp-save-button", "n_clicks"),
    State("active-portfolio-store", "data"),
    State("rp-save-name", "value"),
    State("rp-table", "data"),
    prevent_initial_call=True,
)
def save_rp_portfolio(n_clicks, active_portfolio_data, portfolio_name, rows):
    if not n_clicks:
        return no_update, no_update, no_update
    return _save_rebalance_result(active_portfolio_data, portfolio_name, rows, "rebalance_rp")


@callback(
    Output("cvar-save-status", "children"),
    Output("portfolio-list-store", "data", allow_duplicate=True),
    Output("cvar-save-name", "value"),
    Input("cvar-save-button", "n_clicks"),
    State("active-portfolio-store", "data"),
    State("cvar-save-name", "value"),
    State("cvar-table", "data"),
    prevent_initial_call=True,
)
def save_cvar_portfolio(n_clicks, active_portfolio_data, portfolio_name, rows):
    if not n_clicks:
        return no_update, no_update, no_update
    return _save_rebalance_result(active_portfolio_data, portfolio_name, rows, "rebalance_cvar")



















































layout = html.Div(
    
    className="rb-page",
    children=[
        html.H1("Rebalance portfolia", className="nadpis_predikce"),

        html.Div(
            className="rb-grid",
            children=[
                # ====== LEFT: Mean-Variance ======
                html.Div(
                    className="rb-card",
                    children=[
                        html.H2("Mean–Variance (Markowitz)", className="rb-subtitle"),

                        html.Span(
                            "i",
                            className="rb-info",
                            **{"data-tooltip": "Mean-Variance: hleda vahy ktere maximalizuji E[R] - lambda*risk. Vetsi lambda znamena opatrnejsi portfolio. Weight je podil aktiva. Long-only = bez short pozic."},
                        ),
                        html.Label("Risk aversion (λ)", className="rb-label"),
                        dcc.Slider(
                            id="mv-lambda",
                            min=0.0, max=50.0, step=0.5, value=5.0,
                            marks=None,
                            tooltip={"placement": "bottom", "always_visible": True},
                            className="rb-slider"
                        ),

                        html.Div(
                            className="rb-actions",
                            children=[
                                html.Div(
                                    className="rb-action",
                                    children=[
                                        dcc.Checklist(
                                            id="mv-longonly",
                                            options=[{"label": "Long-only (w ≥ 0)", "value": "LONG"}],
                                            value=["LONG"],
                                            className="rb-checklist",
                                            inputClassName="rb-check-input",
                                            labelClassName="rb-check-label",
                                        )
                                    ],
                                ),
                                html.Div(
                                    className="rb-action",
                                    children=[
                                        html.Button("Spočítat (MV)", id="mv-run", n_clicks=0,
                                                    className="rb-btn rb-pill")
                                    ],
                                ),
                            ],
                        ),

                        html.Div(className="rb-divider"),
                        html.Div(id="mv-status", className="rb-status"),
                        html.Div(
                            className="rb-table-toolbar",
                            children=[
                                dcc.Input(
                                    id="mv-save-name",
                                    type="text",
                                    placeholder="Portfolio name",
                                    debounce=True,
                                    style={
                                        "background": "#111",
                                        "color": "white",
                                        "border": "1px solid rgba(255,255,255,0.18)",
                                        "borderRadius": "8px",
                                        "padding": "8px 10px",
                                        "minWidth": "180px",
                                    },
                                ),
                                html.Button(
                                    "Save as portfolio",
                                    id="mv-save-button",
                                    n_clicks=0,
                                    className="rb-btn rb-pill",
                                    style={"whiteSpace": "nowrap", "width": "50%"},
                                ),
                                dcc.Clipboard(
                                    id="mv-clip",
                                    title="Kopirovat tabulku do schranky",
                                    className="rb-copy-btn",
                                )
                            ],
                        ),
                        html.Div(id="mv-save-status", className="rb-status"),

                        dash_table.DataTable(
                            id="mv-table",
                            columns=[
                                {"name": "Ticker", "id": "ticker"},
                                {"name": "Weight", "id": "weight", "type": "numeric",
                                 "format": {"specifier": ".4f"}},
                            ],
                            data=[],
                            page_size=10,
                            sort_action="native",
                            style_table={"width": "100%", "border": "1px solid rgba(255,255,255,0.25)"},
                            style_header={"textAlign": "center"},
                            style_cell={"textAlign": "center", "border": "1px solid rgba(255,255,255,0.12)"},
                        ),
                    ],
                ),

                # ====== RIGHT: Risk Parity ======
                html.Div(
                    className="rb-card",
                    children=[
                        html.H2("Risk Parity (ERC)", className="rb-subtitle"),

                        html.Span(
                            "i",
                            className="rb-info",
                            **{"data-tooltip": "Risk Parity (ERC): nastavuje vahy tak, aby kazde aktivum podobne prispivalo k riziku. Leverage cap omezuje sumu abs vah. Risk contrib ukazuje prispevek aktiva k riziku."},
                        ),
                        html.Label("Leverage cap (Σ|w|)", className="rb-label"),
                        dcc.Slider(
                            id="rp-gross-cap",
                            min=1.0, max=3.0, step=0.1, value=1.0,
                            marks=None,
                            tooltip={"placement": "bottom", "always_visible": True},
                            className="rb-slider"
                        ),

                        html.Div(
                            className="rb-actions",
                            children=[
                                html.Div(
                                    className="rb-action",
                                    children=[
                                        dcc.Checklist(
                                            id="rp-longonly",
                                            options=[{"label": "Long-only (w ≥ 0)", "value": "LONG"}],
                                            value=["LONG"],
                                            className="rb-checklist",
                                            inputClassName="rb-check-input",
                                            labelClassName="rb-check-label",
                                        )
                                    ],
                                ),
                                html.Div(
                                    className="rb-action",
                                    children=[
                                        html.Button("Spočítat (RP)", id="rp-run", n_clicks=0,
                                                    className="rb-btn rb-pill")
                                    ],
                                ),
                            ],
                        ),

                        html.Div(className="rb-divider"),
                        html.Div(id="rp-status", className="rb-status"),
                        html.Div(
                            className="rb-table-toolbar",
                            children=[
                                dcc.Input(
                                    id="rp-save-name",
                                    type="text",
                                    placeholder="Portfolio name",
                                    debounce=True,
                                    style={
                                        "background": "#111",
                                        "color": "white",
                                        "border": "1px solid rgba(255,255,255,0.18)",
                                        "borderRadius": "8px",
                                        "padding": "8px 10px",
                                        "minWidth": "180px",
                                    },
                                ),
                                html.Button(
                                    "Save as portfolio",
                                    id="rp-save-button",
                                    n_clicks=0,
                                    className="rb-btn rb-pill",
                                    style={"whiteSpace": "nowrap", "width": "50%"},
                                ),
                                dcc.Clipboard(
                                    id="rp-clip",
                                    title="Kopirovat tabulku do schranky",
                                    className="rb-copy-btn",
                                )
                            ],
                        ),
                        html.Div(id="rp-save-status", className="rb-status"),

                        dash_table.DataTable(
                            id="rp-table",
                            columns=[
                                {"name": "Ticker", "id": "ticker"},
                                {"name": "Weight", "id": "weight", "type": "numeric",
                                 "format": {"specifier": ".4f"}},
                                {"name": "Risk contrib", "id": "rc", "type": "numeric",
                                 "format": {"specifier": ".4f"}},
                            ],
                            data=[],
                            page_size=10,
                            sort_action="native",
                            style_table={"width": "100%", "border": "1px solid rgba(255,255,255,0.25)"},
                            style_header={"textAlign": "center"},
                            style_cell={"textAlign": "center", "border": "1px solid rgba(255,255,255,0.12)"},
                        ),
                    ],
                ),

                html.Div(
                    className="rb-card",
                    children=[
                        html.H2("CVaR / Expected Shortfall", className="rb-subtitle"),

                        html.Span(
                            "i",
                            className="rb-info",
                            **{"data-tooltip": "CVaR / Expected Shortfall: minimalizuje prumernou ztratu v nejhorsich scenarich. Alpha urcuje confidence level (napr. 0.95 = nejhorsich 5 procent). Weight je navrzena vaha."},
                        ),
                        html.Label("Confidence level (α)", className="rb-label"),
                        dcc.Slider(
                            id="cvar-alpha",
                            min=0.80, max=0.99, step=0.01, value=0.95,
                            marks=None,
                            tooltip={"placement": "bottom", "always_visible": True},
                            className="rb-slider"
                        ),

                        html.Div(
                            className="rb-actions",
                            children=[
                                html.Div(
                                    className="rb-action",
                                    children=[
                                        dcc.Checklist(
                                            id="cvar-longonly",
                                            options=[{"label": "Long-only (w ≥ 0)", "value": "LONG"}],
                                            value=["LONG"],
                                            className="rb-checklist",
                                            inputClassName="rb-check-input",
                                            labelClassName="rb-check-label",
                                        )
                                    ],
                                ),
                                html.Div(
                                    className="rb-action",
                                    children=[
                                        html.Button("Spočítat (CVaR)", id="cvar-run", n_clicks=0,
                                                    className="rb-btn rb-pill")
                                    ],
                                ),
                            ],
                        ),

                        html.Div(className="rb-divider"),
                        html.Div(id="cvar-status", className="rb-status"),
                        html.Div(
                            className="rb-table-toolbar",
                            children=[
                                dcc.Input(
                                    id="cvar-save-name",
                                    type="text",
                                    placeholder="Portfolio name",
                                    debounce=True,
                                    style={
                                        "background": "#111",
                                        "color": "white",
                                        "border": "1px solid rgba(255,255,255,0.18)",
                                        "borderRadius": "8px",
                                        "padding": "8px 10px",
                                        "minWidth": "180px",
                                    },
                                ),
                                html.Button(
                                    "Save as portfolio",
                                    id="cvar-save-button",
                                    n_clicks=0,
                                    className="rb-btn rb-pill",
                                    style={"whiteSpace": "nowrap", "width": "50%"},
                                ),
                                dcc.Clipboard(
                                    id="cvar-clip",
                                    title="Kopirovat tabulku do schranky",
                                    className="rb-copy-btn",
                                )
                            ],
                        ),
                        html.Div(id="cvar-save-status", className="rb-status"),

                        dash_table.DataTable(
                            id="cvar-table",
                            columns=[
                                {"name": "Ticker", "id": "ticker"},
                                {"name": "Weight", "id": "weight", "type": "numeric",
                                "format": {"specifier": ".4f"}},
                            ],
                            data=[],
                            page_size=10,
                            sort_action="native",
                            style_table={"width": "100%", "border": "1px solid rgba(255,255,255,0.25)"},
                            style_header={"textAlign": "center"},
                            style_cell={"textAlign": "center", "border": "1px solid rgba(255,255,255,0.12)"},
                        ),
                    ],
                ),
            ],
        )
    ],
)
