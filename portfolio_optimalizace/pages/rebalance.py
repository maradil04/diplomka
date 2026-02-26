from dash import register_page, html, dcc, dash_table, Input, Output, State, callback
import pandas as pd
import numpy as np
from scipy.optimize import minimize

register_page(__name__, path="/rebalance")

df_fallback = pd.read_csv("portfolio.csv", sep=None, engine="python")
df = df_fallback.copy()
df_default = df.copy()
tickers = set(df["Ticker"].dropna())
df_prices = pd.read_csv("df_prices.csv")
df_prices_all = pd.read_csv("df_prices.csv")
df_prices["Ticker_clean"] = df_prices["Ticker"].str.split(".").str[0]
df_prices_all = df_prices.copy()

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


@callback(
    Output("mv-table", "data"),
    Output("mv-status", "children"),
    Input("mv-run", "n_clicks"),
    State("stored-data", "data"),
    State("mv-lambda", "value"),
    State("mv-longonly", "value"),
    prevent_initial_call=True
)
def run_rebalance(n_clicks, stored_data, lam, longonly_values):
    long_only = "LONG" in (longonly_values or [])

    # 1) Získej returns
    try:
        if stored_data and isinstance(stored_data, dict) and stored_data.get("returns"):
            rets = pd.read_json(stored_data["returns"], orient="split")
            source = "stored-data['returns']"
        else:
            rets = prices_to_returns(df_prices_all)
            source = "fallback df_prices.csv"
    except Exception as e:
        return [], html.Div(f"Nepodařilo se připravit returns: {e}", style={"color": "crimson"})

    rets = rets.dropna(how="all").dropna(axis=1, how="all")

    if rets.shape[1] < 2 or len(rets) < 10:
        return [], html.Div("Potřebuji alespoň 2 aktiva a dostatek pozorování (>=10).", style={"color": "crimson"})

    # 2) (Volitelné) omez na tickery z portfolia
    try:
        portfolio_tickers = set(df["Ticker"].dropna().astype(str))
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

layout = html.Div(
 
       
    className="rb-page",
    children=[
        
        html.Div(
            className="rb-card",
            children=[
                html.H1("Rebalance portfolia", className="rb-title"),

                html.Div(
                    className="rb-controls",
                    children=[
                        html.Label("Risk aversion (λ)", className="rb-label"),
                        dcc.Slider(
                            id="mv-lambda",
                            min=0.0, max=50.0, step=0.5, value=5.0,
                            marks=None,  # <-- tím odstraníš ty čísla
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
                                        html.Button("Spočítat rebalanci", id="mv-run", n_clicks=0, className="rb-btn rb-pill"),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                html.Div(className="rb-divider"),

                html.Div(id="mv-status", className="rb-status"),

                dash_table.DataTable(
                    id="mv-table",
                    columns=[
                        {"name": "Ticker", "id": "ticker"},
                        {"name": "Weight", "id": "weight", "type": "numeric", "format": {"specifier": ".4f"}},
                    ],
                    data=[],
                    style_table={"width": "100%"},
                    style_cell={"padding": "10px"},
                    style_header={"fontWeight": "600"},
                    page_size=12,
                    sort_action="native",
                ),
            ],
        )
    ],
)