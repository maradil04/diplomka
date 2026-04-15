import pandas as pd


_FALLBACK_EUR_RATES = {
    "EUR": 1.0,
    "USD": 0.92,
    "CNY": 0.127,
    "CNH": 0.127,
    "RMB": 0.127,
    "JPY": 0.0061,
    "CHF": 1.04,
    "CZK": 0.040,
}

_CURRENCY_ALIASES = {
    "EUR": "EUR",
    "€": "EUR",
    "EURO": "EUR",
    "USD": "USD",
    "$": "USD",
    "US DOLLAR": "USD",
    "US DOLLARS": "USD",
    "CNY": "CNY",
    "CNH": "CNH",
    "RMB": "RMB",
    "YUAN": "CNY",
    "YUANS": "CNY",
    "RENMINBI": "CNY",
    "JPY": "JPY",
    "YEN": "JPY",
    "YENS": "JPY",
    "CHF": "CHF",
    "SWISS FRANC": "CHF",
    "SWISS FRANCS": "CHF",
    "CZK": "CZK",
    "CZECH KORUNA": "CZK",
    "CZECH KORUNAS": "CZK",
    "CZECH CROWN": "CZK",
    "CZECH CROWNS": "CZK",
}


def normalize_money_value(value) -> str:
    value = "" if value is None else str(value).strip()
    if not value:
        return ""

    value = value.replace("\u00A0", "").replace(" ", "")
    value = value.replace("€", "").replace("$", "")

    if "," in value and "." not in value:
        head, tail = value.rsplit(",", 1)
        if tail.isdigit() and len(tail) == 3:
            value = head.replace(",", "") + tail
        else:
            value = head.replace(",", "") + "." + tail
    elif "." in value and "," not in value:
        head, tail = value.rsplit(".", 1)
        if tail.isdigit() and len(tail) == 3 and head.replace(".", "").replace("-", "").isdigit():
            value = head.replace(".", "") + tail
    elif "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")

    return "".join(ch for ch in value if ch.isdigit() or ch in ".-")


def parse_money_value(value):
    normalized = normalize_money_value(value)
    if not normalized:
        return None
    try:
        parsed = float(normalized)
    except ValueError:
        return None
    if pd.isna(parsed):
        return None
    return parsed


def normalize_currency_code(value):
    currency = str(value or "").strip().upper()
    if not currency:
        return None
    return _CURRENCY_ALIASES.get(currency, currency)


def convert_amount_to_eur(amount, currency, fx_rate=None):
    parsed_amount = parse_money_value(amount)
    if parsed_amount is None:
        return None

    normalized_currency = normalize_currency_code(currency) or "EUR"
    if normalized_currency == "EUR":
        return round(parsed_amount, 2)

    parsed_fx_rate = parse_money_value(fx_rate)
    if parsed_fx_rate and parsed_fx_rate > 0:
        return round(parsed_amount / parsed_fx_rate, 2)

    fallback_rate = _FALLBACK_EUR_RATES.get(normalized_currency)
    if fallback_rate is None:
        raise ValueError(f"Unsupported currency for EUR conversion: {currency}")
    return round(parsed_amount * fallback_rate, 2)
