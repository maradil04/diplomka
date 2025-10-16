#%%
import requests
import pandas as pd
from time import sleep
tickers = ["EXI2.XETRA", "IS3Q.XETRA", "AMEM.XETRA", "XDWT.XETRA", 
           "DBXJ.XETRA", "IS3K.XETRA", "EXW1.XETRA", "XUCD.XETRA","SXR8.XETRA"]

# Tvůj API klíč
api_token = " 688b41d9701b62.67241962"

# Výstupní složka
output_folder = "data/"

for ticker in tickers:
    url = f"https://eodhistoricaldata.com/api/eod/{ticker}?api_token={api_token}&fmt=json"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if not data:
            print(f"⚠️ Žádná data pro {ticker}")
            continue

        df = pd.DataFrame(data)
        df['ticker'] = ticker
        df.to_csv(f"{output_folder}{ticker}.csv", index=False)
        print(f"✅ Uloženo: {ticker}")

        sleep(1.2)  # kvůli limitu API

    except Exception as e:
        print(f"❌ Chyba pro {ticker}: {e}")
# %%
import pandas as pd
import os

# Cesta ke složce se soubory
folder_path = "data/"

# Seznam všech CSV ve složce
csv_files = [file for file in os.listdir(folder_path) if file.endswith(".csv")]

# Sem budeme ukládat jednotlivé DataFramy
all_data = []

for file in csv_files:
    file_path = os.path.join(folder_path, file)
    df = pd.read_csv(file_path)
    df["Ticker"] = file.replace(".csv", "")  # přidáme sloupec s názvem tickeru
    all_data.append(df)

# Spojení všech do jednoho DataFrame
merged_df = pd.concat(all_data, ignore_index=True)

# Uložení do jednoho CSV
merged_df.to_csv("df_prices.csv", index=False)
print("✅ Uloženo do vsechny_tickers.csv")

# %%
