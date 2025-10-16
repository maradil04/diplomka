#%%
from dash import register_page, html, dcc, dash_table
from dash import Input, Output, callback
import pandas as pd
import plotly.express as px
from datetime import date
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.io as pio
pio.renderers.default = "browser"

#%%
df = pd.read_csv("portfolio.csv")
tickers = set(df["Ticker"])
df_prices = pd.read_csv("df_prices.csv")
df_prices["Ticker_clean"] = df_prices["Ticker"].str.split(".").str[0]
df_prices = df_prices.query("Ticker_clean in @tickers")
print(df.head())
#%%
print(set(df_prices["Ticker_clean"].unique()) & set(df_copy["Ticker"].unique()))

# %%
df = df.sort_values(by = "Date")

df = df[df["Type"].isin(["BUY - MARKET", "SELL - MARKET"])]
df_copy = df.copy()
df_copy["Total_clean"] = (
        df_copy["Total Amount"]
        .astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
    )
df_copy["Total_quant_clean"] = np.where(
        df_copy["Type"].isin(["SELL - MARKET"]),
        -df_copy["Quantity"],
        df_copy["Quantity"]
    )
df_copy["Total_clean"] = df_copy["Total_clean"].astype(float)
df_copy["Total_clean"] = np.where(
    df_copy["Type"].isin(["SELL - MARKET"]),
    -df_copy["Total_clean"],
    df_copy["Total_clean"]

)
df_copy["CumulativeShares"] = df_copy.groupby("Ticker")["Total_quant_clean"].cumsum()



df_copy = df_copy[["Date","Ticker","CumulativeShares"]]

df_copy["Date"] = pd.to_datetime(df_copy["Date"]).dt.tz_localize(None).dt.normalize()
df_prices["date"] = pd.to_datetime(df_prices["date"]).dt.tz_localize(None).dt.normalize()

final = pd.merge(
    df_prices,
    df_copy,
    left_on=["date","Ticker_clean"],
    right_on=["Date","Ticker"],
    how="left"
)

final = final.sort_values(by=["Ticker_clean", "date"])

final["CumulativeShares"] = final.groupby("Ticker_clean")["CumulativeShares"].ffill()

final["position_value"] = final["adjusted_close"] * final["CumulativeShares"]
final["portfolio_value"] = final.groupby("date")["position_value"].transform("sum")
print(final)
#final = final[["date","portfolio_value"]].drop_duplicates()
#%%
# Před samotným vykreslením grafu:
plot_df = final.copy()
plot_df = plot_df.sort_values("date")
plot_df = plot_df.dropna(subset=["portfolio_value"])

# Odfiltruj nulu na začátku (kvůli čáře)
plot_df = plot_df[plot_df["portfolio_value"] > 0]

# Tohle je klíč – zamezí spojení izolované hodnoty se zbytkem
plot_df["prev"] = plot_df["portfolio_value"].shift(1)
plot_df["next"] = plot_df["portfolio_value"].shift(-1)
plot_df = plot_df[(plot_df["prev"].notna()) | (plot_df["next"].notna())]
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=plot_df["date"],
    y=plot_df["portfolio_value"],
    mode="lines",
    name="Portfolio",
    connectgaps=False
))
fig.update_layout(
    title="Hodnota portfolia v čase",
    xaxis_title="Datum",
    yaxis_title="Hodnota (EUR)",
    margin=dict(l=20, r=20, t=40, b=20)
)
fig.show()


# %%
# Zkontroluj podezřelé skoky nebo NaN
df_analyza = final[["date", "portfolio_value"]].copy()

# Přidej posun dopředu a dozadu pro porovnání
df_analyza["prev"] = df_analyza["portfolio_value"].shift(1)
df_analyza["next"] = df_analyza["portfolio_value"].shift(-1)

# Filtruj řádky, kde aktuální hodnota je NaN, ale předchozí nebo následující NENÍ NaN
podezrele = df_analyza[
    (df_analyza["portfolio_value"].isna() & df_analyza["prev"].notna()) |
    (df_analyza["portfolio_value"].isna() & df_analyza["next"].notna()) |
    (df_analyza["portfolio_value"].notna() & df_analyza["prev"].isna()) |
    (df_analyza["portfolio_value"].notna() & df_analyza["next"].isna())
]

# Seřaď podle data
podezrele = podezrele.sort_values("date")
print(podezrele)

# %%
isolated = df_analyza[
    df_analyza["portfolio_value"].notna() &
    df_analyza["portfolio_value"] > 0 &
    df_analyza["portfolio_value"].shift(1).isna() &
    df_analyza["portfolio_value"].shift(-1).isna()
]
print(isolated)

final_date = final["date"].max()
print(final_date)
# %%
################################################x
# %%
print(final_date)
# %%
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

# %%
print(vypocitat_nevyuzity_kapital(final_date, df))
print((final.query("date == @final_date")["portfolio_value"].max()) + vypocitat_nevyuzity_kapital(final_date, df))
# %%
vklady_vybery = df.sort_values(by = "Date")
def investovany_kapital(target_date, df):
    dfx = df.copy()
    amt = (dfx["Total Amount"].astype(str)
             .str.replace("€", "", regex=False)
             .str.replace(",", "", regex=False)
             .str.replace("-", "", regex=False))
    dfx["Total_clean"] = pd.to_numeric(amt, errors="coerce")
    dfx["Total_clean"] = np.where(dfx["Type"].eq("CASH WITHDRAWAL"),
                                 -dfx["Total_clean"], dfx["Total_clean"])
    operace = ["CASH WITHDRAWAL","CASH TOP-UP"]
    dfx = dfx[dfx["Type"].isin(operace)]
    return dfx[["Date","Type","Total_clean"]].reset_index()
print(investovany_kapital(final_date, df))
# %%
