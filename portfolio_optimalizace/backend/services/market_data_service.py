from functools import lru_cache
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_market_data() -> pd.DataFrame:
    return pd.read_csv(PROJECT_ROOT / "df_prices.csv")
