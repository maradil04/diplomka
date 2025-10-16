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
dash.register_page(__name__, path="/predikce")

df_fallback = pd.read_csv("portfolio.csv", sep=None, engine="python")
df = df_fallback.copy()
df_default = df.copy()
tickers = set(df["Ticker"])
df_prices = pd.read_csv("df_prices.csv")
df_prices_all = pd.read_csv("df_prices.csv")
df_prices["Ticker_clean"] = df_prices["Ticker"].str.split(".").str[0]
df_prices_all = df_prices.copy()

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




@callback(
    Output("portfolio_v_case_pred", "children"),
    Input('stored-data', 'data')
)
def graf_portfolio_v_case_pred(stored_data):
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default

    try:
        tickers = set(df["Ticker"])
        prices = df_prices_all.query("Ticker_clean in @tickers")
        result_df = hodnota_portfolia_v_case(df, prices)

        plot_df = result_df.copy()
        plot_df = plot_df.sort_values("date")
        plot_df = plot_df.dropna(subset=["portfolio_value"])
        plot_df = plot_df[plot_df["portfolio_value"] > 0]


        plot_df["prev"] = plot_df["portfolio_value"].shift(1)
        plot_df["next"] = plot_df["portfolio_value"].shift(-1)
        plot_df = plot_df[(plot_df["prev"].notna()) | (plot_df["next"].notna())]

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

from dash import html, dash_table, callback
from dash.dependencies import Output, Input

def df_to_datatable(df: pd.DataFrame):
    # datetime -> text
    for c in df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        df[c] = df[c].dt.strftime("%Y-%m-%d")
    # NaN/NaT -> None
    records = df.where(pd.notnull(df), None).to_dict("records")
    columns = [{"name": c, "id": c} for c in df.columns]
    return dash_table.DataTable(
        data=records,
        columns=columns,
        page_size=20,
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "center", "padding": "8px"},
        filter_action="native",
        sort_action="native",
        fixed_rows={"headers": True},
    )

@callback(
    Output("hodnoty_portfolia_pred", "children"),
    Input("stored-data", "data")
)
def hodnota_portfolia_pred(stored_data):
    if stored_data is not None:
        df = pd.DataFrame(stored_data)
    else:
        df = df_default

    try:
        tickers = set(df["Ticker"])
        prices = df_prices_all.query("Ticker_clean in @tickers")
        result_df = hodnota_portfolia_v_case(df, prices)

        # --- převod DF -> serializovatelná data ---
        df_display = result_df.copy()

        # datetime -> 'YYYY-MM-DD'
        for c in df_display.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
            df_display[c] = df_display[c].dt.strftime("%Y-%m-%d")

        # NaN/NaT -> None
        records = df_display.where(pd.notnull(df_display), None).to_dict("records")

        # --- DataTable (dark theme + card vzhled) ---
        return dash_table.DataTable(
            data=records,
            columns=[{"name": c, "id": c} for c in df_display.columns],
            page_size=20,
            filter_action="native",
            sort_action="native",
            fixed_rows={"headers": True},
            style_table={
                "overflowX": "auto",
                "maxHeight": "600px",
                "overflowY": "auto",
                "border": "1px solid #2c3e50",
                "borderRadius": "12px",
                "boxShadow": "0 8px 24px rgba(0,0,0,0.25)",
            },
            style_cell={
                "textAlign": "center",
                "padding": "8px",
                "fontSize": "14px",
                "fontFamily": "Arial",
                "color": "white",
                "backgroundColor": "#1e1e1e",
                "border": "1px solid #2c3e50",
            },
            style_header={
                "backgroundColor": "#2c3e50",
                "color": "white",
                "fontWeight": "bold",
                "border": "1px solid #2c3e50",
                "position": "sticky",
                "top": 0,
                "zIndex": 1,
            },
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "#2a2a2a"},
                {"if": {"state": "active"}, "backgroundColor": "#3e3e3e", "border": "1px solid #00ff32"},
                # menší font pro hodně široké sloupce:
                {"if": {"column_id": "portfolio_value"}, "fontWeight": "600"},
            ],
        )

    except Exception as e:
        return html.Pre(str(e))





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
    html.H1("Predikce portfolia", className = "nadpis_predikce"),
    
    html.Div(id="portfolio_v_case_pred"),
    html.Div(id="hodnoty_portfolia_pred"),
])
