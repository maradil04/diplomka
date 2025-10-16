import os
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from datetime import date

df = pd.read_csv("data/portfolio_1.csv", delimiter=",")
df["Date"] = pd.to_datetime(df["Date"], utc=True)
dataframe_from_yf = df.copy()



def GetPriceAt(ticker, date_str):
    df_ticker = data_dict.get(ticker)
    if df_ticker is None or df_ticker.empty:
        return None
    date_obj = pd.to_datetime(date_str, utc=True)
    available = df_ticker.index[df_ticker.index <= date_obj]
    if available.empty:
        return None
    return df_ticker.loc[available.max(), "Close"]

def GetValue(target_date):
    target_date = pd.to_datetime(target_date).normalize().tz_localize("UTC")
    df_copy = dataframe_from_yf.copy()  
    df_copy["Date"] = pd.to_datetime(df_copy["Date"], utc=True).dt.normalize()
    df_copy = df_copy[df_copy["Date"] <= target_date] 
    df_copy = df_copy[df_copy["Ticker"].notna()]
    df_copy = df_copy[df_copy["Type"].isin(["BUY - MARKET", "SELL - MARKET"])]
    df_copy["Total_clean"] = (
        df_copy["Total Amount"]
        .astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df_copy = df_copy[df_copy["Total_clean"].str.match(r"^-?\d+(\.\d+)?$")]
    df_copy["Total_clean"] = df_copy["Total_clean"].astype(float)
    df_copy["Total_clean"] = np.where(
        df_copy["Type"].isin(["SELL - MARKET"]),
        -df_copy["Total_clean"],
        df_copy["Total_clean"]
    )
    df_copy["Total_quant_clean"] = np.where(
        df_copy["Type"].isin(["SELL - MARKET"]),
        -df_copy["Quantity"],
        df_copy["Quantity"]
    )
    df_copy["Total_value"] = df_copy.groupby("Ticker")["Total_clean"].transform("sum")
    df_copy["Total_quantity"] = df_copy.groupby("Ticker")["Total_quant_clean"].transform("sum")
    return df_copy[["Ticker", "Total_value", "Total_quantity"]].drop_duplicates()

def CompareValue(target_date):
    start = GetValue(target_date)
    start["Mapped_Ticker"] = start["Ticker"].map(ticker_map)

    prices = []
    for mapped in start["Mapped_Ticker"]:
        if pd.isna(mapped) or mapped not in data_dict:
            prices.append(np.nan)
        else:
            price = GetPriceAt(mapped, target_date)
            prices.append(price if price is not None else np.nan)

    start["Price"] = prices
    start["Price"] = pd.to_numeric(start["Price"], errors="coerce")
    start["Total_quantity"] = pd.to_numeric(start["Total_quantity"], errors="coerce")
    start["Current_value"] = start["Price"] * start["Total_quantity"]
    start["Current_value"] = start["Current_value"].round(2)
    start["Total_quantity"] = start["Total_quantity"].round(2)
    return start[["Ticker", "Total_value", "Price", "Total_quantity","Current_value"]]



def GetInputMoney(target_date):
    target_date = pd.to_datetime(target_date).normalize().tz_localize("UTC")
    df_copy = dataframe_from_yf.copy()
    df_copy["Date"] = pd.to_datetime(df_copy["Date"], utc=True).dt.normalize()
    df_copy = df_copy[df_copy["Date"] <= target_date]

    # Jen CASH TOP-UP a CASH WITHDRAWAL
    df_filtered = df_copy[df_copy["Type"].isin(["CASH TOP-UP", "CASH WITHDRAWAL"])]

    # Čistíme hodnotu, ale nevezmeme znaménko
    df_filtered["Total_clean"] = (
        df_filtered["Total Amount"]
        .astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df_filtered = df_filtered[df_filtered["Total_clean"].str.match(r"^-?\d+(\.\d+)?$")]
    df_filtered["Total_clean"] = df_filtered["Total_clean"].astype(float)

    # Necháváme znaménko tak, jak je
    result = df_filtered.groupby("Type")["Total_clean"].sum().reset_index()
    result.columns = ["Type", "Total_money"]
    return result

def GetFees(target_date):
    target_date = pd.to_datetime(target_date).normalize().tz_localize("UTC")
    df_copy = dataframe_from_yf.copy()
    df_copy["Date"] = pd.to_datetime(df_copy["Date"], utc=True).dt.normalize()
    df_copy = df_copy[df_copy["Date"] <= target_date]

    # Jen CASH TOP-UP a CASH WITHDRAWAL
    df_filtered = df_copy[df_copy["Type"].str.contains("FEE")]

    # Čistíme hodnotu, ale nevezmeme znaménko
    df_filtered["Total_clean"] = (
        df_filtered["Total Amount"]
        .astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df_filtered = df_filtered[df_filtered["Total_clean"].str.match(r"^-?\d+(\.\d+)?$")]
    df_filtered["Total_clean"] = df_filtered["Total_clean"].astype(float)

    # Necháváme znaménko tak, jak je
    result = df_filtered.groupby("Type")["Total_clean"].sum().reset_index()
    result.columns = ["Type", "Total_money"]
    return result
