import io
import json
import math
import base64
from pathlib import Path
from datetime import datetime

import pandas as pd

from backend.repositories.portfolios import update_portfolio_metadata
from backend.repositories.transactions import replace_portfolio_transactions
from backend.services.currency_conversion_service import convert_amount_to_eur


CANONICAL_IMPORT_COLUMNS = [
    "Date",
    "Ticker",
    "Type",
    "Quantity",
    "Price per share",
    "Total Amount",
    "Currency",
    "FX Rate",
]
DISPLAY_IMPORT_COLUMNS = [
    "Date",
    "Ticker",
    "Type",
    "Quantity",
    "Price per share",
    "Total Amount",
    "Currency",
]
REQUIRED_IMPORT_COLUMNS = ["Date", "Type", "Total Amount", "Currency"]
REQUIRED_BY_TYPE = {
    "BUY - MARKET": ["Ticker", "Quantity"],
    "SELL - MARKET": ["Ticker", "Quantity"],
}
OPTIONAL_BLANK_BY_TYPE = {
    "CASH TOP-UP": {"Ticker", "Quantity", "Price per share"},
    "CASH WITHDRAWAL": {"Ticker", "Quantity", "Price per share"},
    "ROBO MANAGEMENT FEE": {"Ticker", "Quantity", "Price per share"},
    "DIVIDEND": {"Quantity", "Price per share"},
}
TYPE_ALIASES = {
    "buy-market": "BUY - MARKET",
    "buy market": "BUY - MARKET",
    "buy_market": "BUY - MARKET",
    "buy": "BUY - MARKET",
    "sell-market": "SELL - MARKET",
    "sell market": "SELL - MARKET",
    "sell_market": "SELL - MARKET",
    "sell": "SELL - MARKET",
    "cash top-up": "CASH TOP-UP",
    "cash top up": "CASH TOP-UP",
    "cash_top_up": "CASH TOP-UP",
    "top-up": "CASH TOP-UP",
    "top up": "CASH TOP-UP",
    "cash withdrawal": "CASH WITHDRAWAL",
    "cash-withdrawal": "CASH WITHDRAWAL",
    "cash_withdrawal": "CASH WITHDRAWAL",
    "withdrawal": "CASH WITHDRAWAL",
    "robo management fee": "ROBO MANAGEMENT FEE",
    "management fee": "ROBO MANAGEMENT FEE",
    "fee": "ROBO MANAGEMENT FEE",
    "dividend": "DIVIDEND",
    "dividends": "DIVIDEND",
}
COLUMN_ALIASES = {
    "date": "Date",
    "datum": "Date",
    "ticker": "Ticker",
    "symbol": "Ticker",
    "asset": "Ticker",
    "type": "Type",
    "transaction type": "Type",
    "operation": "Type",
    "quantity": "Quantity",
    "qty": "Quantity",
    "shares": "Quantity",
    "price per share": "Price per share",
    "price/share": "Price per share",
    "price": "Price per share",
    "unit price": "Price per share",
    "total amount": "Total Amount",
    "amount": "Total Amount",
    "total": "Total Amount",
    "value": "Total Amount",
    "currency": "Currency",
    "curr": "Currency",
    "fx rate": "FX Rate",
    "fx": "FX Rate",
    "exchange rate": "FX Rate",
}


def _normalize_label(value):
    return " ".join(str(value or "").strip().replace("_", " ").split()).lower()


def _normalize_type(value):
    normalized = _normalize_label(value).replace(" - ", " ").replace("-", " ")
    return TYPE_ALIASES.get(normalized)


def _clean_text_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return str(value).strip() or None


def _money_to_float(value):
    cleaned = _clean_text_value(value)
    if cleaned is None:
        return None
    normalized = cleaned.replace("\u00A0", "").replace(" ", "")
    normalized = normalized.replace("€", "").replace("â‚¬", "").replace("EUR", "").replace("eur", "")
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        parts = normalized.rsplit(",", 1)
        normalized = parts[0].replace(",", "") + "." + parts[1]
    normalized = "".join(ch for ch in normalized if ch.isdigit() or ch in ".-")
    if normalized in {"", "-", ".", "-."}:
        return None
    return float(normalized)


def _value_present(value):
    return _clean_text_value(value) is not None


def _decode_upload_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV file could not be decoded. Please export it as UTF-8 CSV.")


def validate_upload_filename(filename: str) -> None:
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix != ".csv":
        raise ValueError("Neplatny format souboru.")


def _canonicalize_columns(dataframe: pd.DataFrame):
    rename_map = {}
    autocorrections = []
    for column in dataframe.columns:
        normalized = _normalize_label(column)
        canonical = COLUMN_ALIASES.get(normalized)
        if canonical:
            rename_map[column] = canonical
            if column != canonical:
                autocorrections.append(f"Renamed column '{column}' to '{canonical}'.")
    if rename_map:
        dataframe = dataframe.rename(columns=rename_map)
    return dataframe, autocorrections


def _ensure_expected_columns(dataframe: pd.DataFrame):
    missing = [column for column in REQUIRED_IMPORT_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValueError(
            "Missing required CSV columns: "
            + ", ".join(missing)
            + ". Required columns are: "
            + ", ".join(REQUIRED_IMPORT_COLUMNS)
            + ". Optional columns are: "
            + ", ".join(column for column in DISPLAY_IMPORT_COLUMNS if column not in REQUIRED_IMPORT_COLUMNS)
            + ". FX Rate is accepted when present but is not required and is not used for EUR conversion."
        )

    duplicate_columns = dataframe.columns[dataframe.columns.duplicated()].tolist()
    if duplicate_columns:
        raise ValueError(f"CSV contains duplicate columns: {', '.join(duplicate_columns)}")

    for column in CANONICAL_IMPORT_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = None
    return dataframe[CANONICAL_IMPORT_COLUMNS]


def _normalize_dataframe_values(dataframe: pd.DataFrame):
    working = dataframe.copy()
    autocorrections = []

    for column in working.columns:
        if working[column].dtype == object:
            working[column] = working[column].apply(_clean_text_value)

    parsed_dates = pd.to_datetime(working["Date"], errors="coerce", utc=True)
    invalid_dates = parsed_dates.isna()
    if invalid_dates.any():
        line_numbers = ", ".join(str(index + 2) for index in working.index[invalid_dates][:5])
        raise ValueError(f"Invalid Date values on CSV lines: {line_numbers}.")
    working["Date"] = parsed_dates.dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    normalized_types = working["Type"].apply(_normalize_type)
    invalid_types = normalized_types.isna()
    if invalid_types.any():
        invalid_values = sorted({_clean_text_value(value) or "<blank>" for value in working.loc[invalid_types, "Type"].tolist()})
        raise ValueError(
            "Unsupported Type values: "
            + ", ".join(invalid_values[:8])
            + ". Allowed values are: "
            + ", ".join(sorted(REQUIRED_BY_TYPE.keys() | OPTIONAL_BLANK_BY_TYPE.keys()))
        )
    type_changed = normalized_types != working["Type"]
    if type_changed.any():
        autocorrections.append("Normalized transaction Type values to the expected uppercase format.")
    working["Type"] = normalized_types

    if "Ticker" in working.columns:
        cleaned_tickers = working["Ticker"].apply(lambda value: _clean_text_value(value).upper() if _clean_text_value(value) else None)
        if (cleaned_tickers != working["Ticker"]).fillna(False).any():
            autocorrections.append("Normalized ticker symbols to uppercase.")
        working["Ticker"] = cleaned_tickers

    if "Currency" in working.columns:
        cleaned_currency = working["Currency"].apply(lambda value: _clean_text_value(value).upper() if _clean_text_value(value) else None)
        if (cleaned_currency != working["Currency"]).fillna(False).any():
            autocorrections.append("Normalized currency codes to uppercase.")
        working["Currency"] = cleaned_currency

    return working, autocorrections


def _validate_row_requirements(dataframe: pd.DataFrame):
    errors = []

    blank_required = dataframe["Total Amount"].apply(lambda value: _money_to_float(value) is None)
    if blank_required.any():
        lines = ", ".join(str(index + 2) for index in dataframe.index[blank_required][:5])
        errors.append(f"Column 'Total Amount' must contain a numeric value on lines: {lines}.")

    blank_currency = dataframe["Currency"].apply(lambda value: not _value_present(value))
    if blank_currency.any():
        lines = ", ".join(str(index + 2) for index in dataframe.index[blank_currency][:5])
        errors.append(f"Column 'Currency' is required on lines: {lines}.")

    quantity_series = dataframe["Quantity"].apply(_money_to_float)

    for transaction_type, required_columns in REQUIRED_BY_TYPE.items():
        mask = dataframe["Type"].eq(transaction_type)
        if not mask.any():
            continue
        for column in required_columns:
            if column == "Quantity":
                invalid = mask & quantity_series.isna()
            else:
                invalid = mask & ~dataframe[column].apply(_value_present)
            if invalid.any():
                lines = ", ".join(str(index + 2) for index in dataframe.index[invalid][:5])
                errors.append(f"Type '{transaction_type}' requires '{column}' on lines: {lines}.")

    if errors:
        raise ValueError(" ".join(errors))


def _validate_dataframe(dataframe: pd.DataFrame):
    if dataframe.empty:
        raise ValueError("CSV file is empty.")
    _validate_row_requirements(dataframe)


def parse_transactions_csv(decoded_text: str) -> pd.DataFrame:
    dataframe = pd.read_csv(io.StringIO(decoded_text), sep=None, engine="python")
    dataframe, column_autocorrections = _canonicalize_columns(dataframe)
    dataframe = _ensure_expected_columns(dataframe)
    dataframe, value_autocorrections = _normalize_dataframe_values(dataframe)
    _validate_dataframe(dataframe)
    dataframe.attrs["import_warnings"] = column_autocorrections + value_autocorrections
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
                "total_amount": _convert_total_amount_to_eur_string(cleaned),
                "total_amount_original_curr": cleaned.get("Total Amount"),
                "currency": cleaned.get("Currency"),
                "raw_json": json.dumps(cleaned, ensure_ascii=True),
            }
        )
    return records


def _convert_total_amount_to_eur_string(cleaned_row):
    converted = convert_amount_to_eur(
        cleaned_row.get("Total Amount"),
        cleaned_row.get("Currency"),
    )
    if converted is None:
        return None
    return f"{converted:.2f}"


def parse_upload_contents(contents: str, filename: str | None = None) -> pd.DataFrame:
    if not contents:
        raise ValueError("Upload contents are empty.")
    validate_upload_filename(filename)
    _content_type, content_string = contents.split(",", 1)
    decoded = io.BytesIO(base64.b64decode(content_string))
    text = _decode_upload_text(decoded.getvalue())
    return parse_transactions_csv(text)


def import_transactions_dataframe(*, portfolio_id, dataframe: pd.DataFrame, filename=None, market_data_summary=None):
    transaction_records = dataframe_to_transaction_records(dataframe)
    replace_portfolio_transactions(
        portfolio_id=portfolio_id,
        transaction_records=transaction_records,
        filename=filename,
    )
    effective_start_date = None
    if market_data_summary and market_data_summary.get("overlap_start") is not None:
        effective_start_date = str(market_data_summary["overlap_start"])
    update_portfolio_metadata(
        portfolio_id=portfolio_id,
        source_filename=filename,
        effective_start_date=effective_start_date,
    )
    return dataframe
