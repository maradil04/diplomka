import io
import json
import math
import base64
from datetime import datetime

import pandas as pd

from backend.repositories.portfolios import update_portfolio_metadata
from backend.repositories.transactions import replace_portfolio_transactions


REQUIRED_IMPORT_COLUMNS = ["Date", "Type"]


def parse_transactions_csv(decoded_text: str) -> pd.DataFrame:
    dataframe = pd.read_csv(io.StringIO(decoded_text), sep=None, engine="python")
    missing = [column for column in REQUIRED_IMPORT_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Missing required CSV columns: {', '.join(missing)}")
    return dataframe


def dataframe_to_transaction_records(dataframe: pd.DataFrame):
    def _clean_value(value):
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()
        if isinstance(value, float) and math.isnan(value):
            return None
        return value

    records = []
    for row in dataframe.to_dict("records"):
        cleaned = {key: _clean_value(value) for key, value in row.items()}
        records.append(
            {
                "date": cleaned.get("Date"),
                "ticker": cleaned.get("Ticker"),
                "type": cleaned.get("Type") or "UNKNOWN",
                "quantity": cleaned.get("Quantity"),
                "total_amount": cleaned.get("Total Amount"),
                "currency": cleaned.get("Currency"),
                "raw_json": json.dumps(cleaned, ensure_ascii=True),
            }
        )
    return records


def parse_upload_contents(contents: str) -> pd.DataFrame:
    if not contents:
        raise ValueError("Upload contents are empty.")
    _content_type, content_string = contents.split(",", 1)
    decoded = io.BytesIO(base64.b64decode(content_string))
    text = decoded.getvalue().decode("utf-8")
    return parse_transactions_csv(text)


def import_transactions_dataframe(*, portfolio_id, dataframe: pd.DataFrame, filename=None):
    transaction_records = dataframe_to_transaction_records(dataframe)
    replace_portfolio_transactions(
        portfolio_id=portfolio_id,
        transaction_records=transaction_records,
        filename=filename,
    )
    update_portfolio_metadata(portfolio_id=portfolio_id, source_filename=filename)
    return dataframe
