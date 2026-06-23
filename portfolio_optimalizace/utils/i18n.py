from __future__ import annotations

from typing import Any


DEFAULT_LANGUAGE = "cs"
SUPPORTED_LANGUAGES = ("cs", "en")


TRANSLATIONS: dict[str, dict[str, str]] = {
    "app.menu": {
        "cs": "Menu",
        "en": "Menu",
    },
    "app.close": {
        "cs": "Zavřít",
        "en": "Close",
    },
    "app.portfolio": {
        "cs": "Portfolio",
        "en": "Portfolio",
    },
    "app.dashboard": {
        "cs": "Dashboard",
        "en": "Dashboard",
    },
    "app.prediction": {
        "cs": "Predikce",
        "en": "Prediction",
    },
    "app.rebalance": {
        "cs": "Rebalance",
        "en": "Rebalance",
    },
    "app.waiting_overlay": {
        "cs": "ČEKÁNÍ NA VLOŽENÍ PORTFOLIA",
        "en": "WAITING FOR PORTFOLIO IMPORT",
    },
    "auth.continue_google": {
        "cs": "Pokračovat přes Google",
        "en": "Continue with Google",
    },
    "auth.signed_in_as": {
        "cs": "Přihlášen jako {name}",
        "en": "Signed in as {name}",
    },
    "auth.logout": {
        "cs": "Odhlásit se",
        "en": "Log out",
    },
    "auth.user": {
        "cs": "Uživatel",
        "en": "User",
    },
    "sidebar.language": {
        "cs": "Jazyk",
        "en": "Language",
    },
    "sidebar.language_cs": {
        "cs": "Čeština 🇨🇿",
        "en": "Čeština 🇨🇿",
    },
    "sidebar.language_en": {
        "cs": "English 🇬🇧",
        "en": "English 🇬🇧",
    },
    "sidebar.portfolios": {
        "cs": "Portfolia",
        "en": "Portfolios",
    },
    "sidebar.context": {
        "cs": "Globální kontext portfolia pro dashboard, predikci a rebalance.",
        "en": "Global portfolio context for dashboard, prediction, and rebalance.",
    },
    "sidebar.select_date": {
        "cs": "Vyber datum",
        "en": "Select date",
    },
    "sidebar.import_csv": {
        "cs": "Import CSV",
        "en": "Import CSV",
    },
    "sidebar.import_header": {
        "cs": "Nahraj CSV s těmito sloupci v hlavičce:",
        "en": "Upload a CSV with these columns in the header:",
    },
    "sidebar.import_required": {
        "cs": "Povinné hodnoty: Date, Type, Total Amount, Currency. Řádky Buy a Sell musí navíc obsahovat Ticker a Quantity.",
        "en": "Required values: Date, Type, Total Amount, Currency. Buy and Sell rows must also contain Ticker and Quantity.",
    },
    "sidebar.import_types": {
        "cs": "Povolené hodnoty Type: BUY - MARKET, SELL - MARKET, CASH TOP-UP, CASH WITHDRAWAL, ROBO MANAGEMENT FEE, DIVIDEND.",
        "en": "Accepted Type values: BUY - MARKET, SELL - MARKET, CASH TOP-UP, CASH WITHDRAWAL, ROBO MANAGEMENT FEE, DIVIDEND.",
    },
    "sidebar.import_note": {
        "cs": "Sloupec FX Rate není povinný a pro přepočet se nepoužívá. Částky mimo EUR se převádějí do EUR pomocí přibližných vestavěných kurzů. Importer umí opravit kapitalizaci a běžné varianty názvů sloupců.",
        "en": "FX Rate is not required and is not used for conversion. Non-EUR amounts are converted to EUR using approximate built-in rates. The importer can auto-fix capitalization and common column-name variants.",
    },
    "sidebar.choose_csv": {
        "cs": "Vybrat CSV soubor",
        "en": "Choose CSV file",
    },
    "sidebar.export_pdf": {
        "cs": "Export PDF reportu",
        "en": "Export PDF report",
    },
    "sidebar.portfolio_name": {
        "cs": "Název portfolia",
        "en": "Portfolio name",
    },
    "sidebar.create": {
        "cs": "Vytvořit",
        "en": "Create",
    },
    "sidebar.no_portfolios": {
        "cs": "Zatím žádná portfolia.",
        "en": "No portfolios yet.",
    },
    "sidebar.active_hint": {
        "cs": "Aktivní portfolio řídí všechny analytické stránky.",
        "en": "Active portfolio drives all analysis pages.",
    },
    "common.authentication_required": {
        "cs": "Je vyžadováno přihlášení.",
        "en": "Authentication required.",
    },
    "common.no_active_portfolio": {
        "cs": "Není vybráno žádné aktivní portfolio.",
        "en": "No active portfolio selected.",
    },
    "common.select_date_for_calc": {
        "cs": "Vyber datum pro výpočet portfolia.",
        "en": "Select a date for portfolio calculation.",
    },
    "common.no_transactions": {
        "cs": "Portfolio zatím neobsahuje importované transakce.",
        "en": "Portfolio has no imported transactions yet.",
    },
    "common.choose_assets": {
        "cs": "Nebyla vybrána žádná aktiva.",
        "en": "No assets were selected.",
    },
    "common.error": {
        "cs": "Chyba: {error}",
        "en": "Error: {error}",
    },
    "index.portfolio_select_failed": {
        "cs": "Portfolio se nepodařilo vybrat.",
        "en": "Portfolio could not be selected.",
    },
    "index.active_portfolio": {
        "cs": "Aktivní portfolio: {name}",
        "en": "Active portfolio: {name}",
    },
    "index.portfolio_deleted": {
        "cs": "Portfolio bylo smazáno.",
        "en": "Portfolio deleted.",
    },
    "index.portfolio_deleted_active": {
        "cs": "Portfolio bylo smazáno. Aktivní portfolio: {name}",
        "en": "Portfolio deleted. Active portfolio: {name}",
    },
    "index.created_portfolio": {
        "cs": "Vytvořeno portfolio: {name}",
        "en": "Created portfolio: {name}",
    },
    "index.report_generated": {
        "cs": "PDF report byl vygenerován: {filename}",
        "en": "PDF report generated: {filename}",
    },
    "index.report_failed": {
        "cs": "Export PDF selhal: {error}",
        "en": "PDF export failed: {error}",
    },
    "home.title": {
        "cs": "Analýza portfolia",
        "en": "Portfolio Analysis",
    },
    "home.subtitle": {
        "cs": "Školní projekt - testovací verze",
        "en": "Academic project - testing version",
    },
    "home.section.portfolio_table": {
        "cs": "Souhrnná tabulka portfolia",
        "en": "Portfolio Summary Table",
    },
    "home.section.asset_risk": {
        "cs": "Ukazatele rizika",
        "en": "Risk Metrics",
    },
    "home.section.value_history": {
        "cs": "Hodnota portfolia v čase",
        "en": "Portfolio Value Over Time",
    },
    "home.section.asset_selection": {
        "cs": "Výběr aktiv",
        "en": "Asset Selection",
    },
    "home.section.benchmark_compare": {
        "cs": "Porovnání s benchmarky",
        "en": "Benchmark Comparison",
    },
    "home.section.breakdown": {
        "cs": "Složení portfolia a poplatky",
        "en": "Portfolio Breakdown and Fees",
    },
    "home.section.monthly_dividends": {
        "cs": "Dividendy po měsících",
        "en": "Dividends by Month",
    },
    "home.frequency_label": {
        "cs": "Vyber frekvenci dat:",
        "en": "Choose data frequency:",
    },
    "home.frequency.daily": {
        "cs": "Denní",
        "en": "Daily",
    },
    "home.frequency.monthly": {
        "cs": "Měsíční",
        "en": "Monthly",
    },
    "home.assets_label": {
        "cs": "Vyber aktiva:",
        "en": "Choose assets:",
    },
    "home.start_date_label": {
        "cs": "Vyber počáteční datum:",
        "en": "Choose start date:",
    },
    "home.compare_label": {
        "cs": "Vyber aktiva na porovnání:",
        "en": "Choose assets for comparison:",
    },
    "home.allocation_title": {
        "cs": "Alokace aktiv v portfoliu",
        "en": "Portfolio Asset Allocation",
    },
    "home.passive_income_title": {
        "cs": "Pasivní příjmy a výdaje portfolia",
        "en": "Portfolio Passive Income and Expenses",
    },
    "home.no_valid_data": {
        "cs": "Žádná platná data pro zadané datum.",
        "en": "No valid data for the selected date.",
    },
    "home.portfolio": {
        "cs": "Portfolio",
        "en": "Portfolio",
    },
    "home.cashflow": {
        "cs": "Cashflow",
        "en": "Cashflow",
    },
    "home.purchased_value": {
        "cs": "CELKOVÁ KUPNÍ HODNOTA",
        "en": "TOTAL PURCHASE VALUE",
    },
    "home.current_value": {
        "cs": "CELKOVÁ SOUČASNÁ HODNOTA",
        "en": "TOTAL CURRENT VALUE",
    },
    "home.total_quantity": {
        "cs": "CELKOVÝ POČET",
        "en": "TOTAL QUANTITY",
    },
    "home.avg_purchase_price": {
        "cs": "PRŮMĚRNÁ NÁKUPNÍ CENA",
        "en": "AVERAGE PURCHASE PRICE",
    },
    "home.dividend": {
        "cs": "DIVIDENDA",
        "en": "DIVIDEND",
    },
    "home.profit": {
        "cs": "PROFIT",
        "en": "PROFIT",
    },
    "home.total_portfolio_value": {
        "cs": "CELKOVÁ HODNOTA PORTFOLIA",
        "en": "TOTAL PORTFOLIO VALUE",
    },
    "home.total_invested": {
        "cs": "CELKOVĚ INVESTOVÁNO",
        "en": "TOTAL INVESTED",
    },
    "home.total_return": {
        "cs": "CELKOVÝ VÝNOS PORTFOLIA",
        "en": "TOTAL PORTFOLIO RETURN",
    },
    "home.annualized_return": {
        "cs": "ANUALIZOVANÝ VÝNOS",
        "en": "ANNUALIZED RETURN",
    },
    "home.max_drawdown": {
        "cs": "MAX DRAWDOWN",
        "en": "MAX DRAWDOWN",
    },
    "home.portfolio_volatility": {
        "cs": "VOLATILITA PORTFOLIA",
        "en": "PORTFOLIO VOLATILITY",
    },
    "home.volatility": {
        "cs": "Volatilita",
        "en": "Volatility",
    },
    "home.relative_prices": {
        "cs": "Relativní vývoj cen aktiv portfolia (počátek = 100)",
        "en": "Relative Price Performance of Portfolio Assets (start = 100)",
    },
    "home.assets_legend": {
        "cs": "Aktiva",
        "en": "Assets",
    },
    "home.date": {
        "cs": "Datum",
        "en": "Date",
    },
    "home.indexed_price": {
        "cs": "Indexovaná cena",
        "en": "Indexed Price",
    },
    "home.normalized_compare": {
        "cs": "Normalizovaná hodnota portfolia + porovnání",
        "en": "Normalized Portfolio Value + Comparison",
    },
    "home.index_base_100": {
        "cs": "Index (base = 100)",
        "en": "Index (base = 100)",
    },
    "home.portfolio_value_history": {
        "cs": "Hodnota portfolia v čase",
        "en": "Portfolio Value Over Time",
    },
    "home.value_eur": {
        "cs": "Hodnota (EUR)",
        "en": "Value (EUR)",
    },
    "home.monthly_dividend_missing_data": {
        "cs": "Chybí data pro výpočet měsíčních dividend.",
        "en": "Missing data for monthly dividend calculation.",
    },
    "home.monthly_dividend_missing_dates": {
        "cs": "Chybí validní datumy pro časovou osu.",
        "en": "Missing valid dates for the timeline.",
    },
    "home.monthly_dividend_income": {
        "cs": "Měsíční dividendový příjem",
        "en": "Monthly Dividend Income",
    },
    "home.month": {
        "cs": "Měsíc",
        "en": "Month",
    },
    "home.amount": {
        "cs": "Částka",
        "en": "Amount",
    },
    "home.upload_success": {
        "cs": "Do vybraného portfolia bylo importováno {rows} řádků.",
        "en": "Imported {rows} rows into the selected portfolio.",
    },
    "home.market_data_downloaded": {
        "cs": "Stažená tržní data pro: {tickers}.",
        "en": "Downloaded market data for: {tickers}.",
    },
    "home.price_overlap": {
        "cs": "Okno cenového překryvu: {start} až {end}.",
        "en": "Price overlap window: {start} to {end}.",
    },
    "home.autocorrections": {
        "cs": "Automatické opravy: {warnings}",
        "en": "Autocorrections: {warnings}",
    },
    "home.upload_failed": {
        "cs": "Nahrání selhalo. {error}",
        "en": "Upload failed. {error}",
    },
    "pred.page_title": {
        "cs": "Predikce jednotlivých aktiv a portfolia",
        "en": "Prediction of Individual Assets and Portfolio",
    },
    "pred.portfolio_title": {
        "cs": "ARIMA predikce celého portfolia:",
        "en": "ARIMA forecast for the whole portfolio:",
    },
    "pred.run_portfolio": {
        "cs": "Spustit predikci portfolia",
        "en": "Run portfolio prediction",
    },
    "pred.portfolio_header": {
        "cs": "Predikce - Portfolio",
        "en": "Prediction - Portfolio",
    },
    "pred.click_to_run": {
        "cs": "Klikněte na tlačítko pro spuštění predikce aktivního portfolia.",
        "en": "Click the button to run prediction for the active portfolio.",
    },
    "pred.asset_title": {
        "cs": "ARIMA predikce cen:",
        "en": "ARIMA price forecast:",
    },
    "pred.missing_portfolio_data": {
        "cs": "V uploadovaném souboru chybí data portfolia.",
        "en": "Portfolio data is missing in the uploaded file.",
    },
    "pred.missing_price_data": {
        "cs": "Nenalezena cenová data pro tickery z portfolia.",
        "en": "Price data for portfolio tickers was not found.",
    },
    "pred.insufficient_cf_data": {
        "cs": "Nedostatek dat pro výpočet cash-flow-adjusted výkonnosti portfolia.",
        "en": "Insufficient data to compute cash-flow-adjusted portfolio performance.",
    },
    "pred.too_few_cf_obs": {
        "cs": "Málo cash-flow-adjusted pozorování ({count}), minimum je {minimum}.",
        "en": "Too few cash-flow-adjusted observations ({count}); minimum is {minimum}.",
    },
    "pred.cf_history": {
        "cs": "Cash-flow-adjusted historie - {ticker}",
        "en": "Cash-flow-adjusted history - {ticker}",
    },
    "pred.too_few_returns": {
        "cs": "Málo returnů ({count}), minimum je {minimum}.",
        "en": "Too few returns ({count}); minimum is {minimum}.",
    },
    "pred.no_stable_arima": {
        "cs": "Nepodařilo se najít stabilní ARIMA model.",
        "en": "Could not find a stable ARIMA model.",
    },
    "pred.history": {
        "cs": "{ticker} - historie",
        "en": "{ticker} - history",
    },
    "pred.forecast_mean": {
        "cs": "{ticker} - predikce (mean)",
        "en": "{ticker} - forecast (mean)",
    },
    "pred.volatility_band": {
        "cs": "Volatilní pásmo ±1σ",
        "en": "Volatility band ±1σ",
    },
    "pred.portfolio_chart_title": {
        "cs": "{ticker}: predikce ceny + volatilní pásmo | {extra}",
        "en": "{ticker}: price forecast + volatility band | {extra}",
    },
    "pred.price_chart_title": {
        "cs": "{ticker}: predikce ceny + volatilní pásmo | {extra}",
        "en": "{ticker}: price forecast + volatility band | {extra}",
    },
    "pred.prediction_failed": {
        "cs": "Predikce selhala: {error}",
        "en": "Prediction failed: {error}",
    },
    "pred.select_stock": {
        "cs": "Vyberte akcii v dropdownu.",
        "en": "Select a stock in the dropdown.",
    },
    "pred.price_band_header": {
        "cs": "Predikce ceny + volatilní pásmo",
        "en": "Price forecast + volatility band",
    },
    "pred.no_data_for": {
        "cs": "Žádná data pro {ticker}.",
        "en": "No data for {ticker}.",
    },
    "pred.too_few_price_obs": {
        "cs": "Málo cenových pozorování ({count}), minimum je {minimum}.",
        "en": "Too few price observations ({count}); minimum is {minimum}.",
    },
    "pred.price_history": {
        "cs": "Historie ceny - {ticker}",
        "en": "Price history - {ticker}",
    },
    "pred.date": {
        "cs": "Datum",
        "en": "Date",
    },
    "pred.price": {
        "cs": "Cena",
        "en": "Price",
    },
    "rebalance.page_title": {
        "cs": "Rebalance portfolia",
        "en": "Portfolio Rebalance",
    },
    "rebalance.mv_info": {
        "cs": "Mean-Variance: hledá váhy, které maximalizují E[R] - lambda*risk. Větší lambda znamená opatrnější portfolio. Weight je podíl aktiva. Long-only = bez short pozic.",
        "en": "Mean-Variance: searches for weights that maximize E[R] - lambda*risk. Higher lambda means a more conservative portfolio. Weight is the asset share. Long-only = no short positions.",
    },
    "rebalance.rp_info": {
        "cs": "Risk Parity (ERC): nastavuje váhy tak, aby každé aktivum podobně přispívalo k riziku. Leverage cap omezuje sumu abs vah. Risk contrib ukazuje příspěvek aktiva k riziku.",
        "en": "Risk Parity (ERC): sets weights so that each asset contributes similarly to risk. Leverage cap limits the sum of absolute weights. Risk contrib shows each asset contribution to risk.",
    },
    "rebalance.cvar_info": {
        "cs": "CVaR / Expected Shortfall: minimalizuje průměrnou ztrátu v nejhorších scénářích. Alpha určuje confidence level (např. 0.95 = nejhorších 5 procent). Weight je navržená váha.",
        "en": "CVaR / Expected Shortfall: minimizes average loss in the worst scenarios. Alpha sets the confidence level (for example 0.95 = worst 5 percent). Weight is the proposed asset weight.",
    },
    "rebalance.risk_aversion": {
        "cs": "Risk aversion (λ)",
        "en": "Risk aversion (λ)",
    },
    "rebalance.leverage_cap": {
        "cs": "Leverage cap (Σ|w|)",
        "en": "Leverage cap (Σ|w|)",
    },
    "rebalance.confidence_level": {
        "cs": "Confidence level (α)",
        "en": "Confidence level (α)",
    },
    "rebalance.long_only": {
        "cs": "Long-only (w ≥ 0)",
        "en": "Long-only (w ≥ 0)",
    },
    "rebalance.calculate_mv": {
        "cs": "Spočítat (MV)",
        "en": "Calculate (MV)",
    },
    "rebalance.calculate_rp": {
        "cs": "Spočítat (RP)",
        "en": "Calculate (RP)",
    },
    "rebalance.calculate_cvar": {
        "cs": "Spočítat (CVaR)",
        "en": "Calculate (CVaR)",
    },
    "rebalance.save_as_portfolio": {
        "cs": "Uložit jako portfolio",
        "en": "Save as portfolio",
    },
    "rebalance.copy_table": {
        "cs": "Kopírovat tabulku do schránky",
        "en": "Copy table to clipboard",
    },
    "rebalance.ticker": {
        "cs": "Ticker",
        "en": "Ticker",
    },
    "rebalance.weight": {
        "cs": "Weight",
        "en": "Weight",
    },
    "rebalance.risk_contrib": {
        "cs": "Risk contrib",
        "en": "Risk contrib",
    },
    "rebalance.select_source_first": {
        "cs": "Nejprve vyber zdrojové portfolio.",
        "en": "Select a source portfolio first.",
    },
    "rebalance.saved_portfolio": {
        "cs": "Uloženo portfolio: {name}",
        "en": "Saved portfolio: {name}",
    },
    "rebalance.save_failed": {
        "cs": "Uložení selhalo: {error}",
        "en": "Save failed: {error}",
    },
    "rebalance.prepare_returns_failed": {
        "cs": "Nepodařilo se připravit returns: {error}",
        "en": "Failed to prepare returns: {error}",
    },
    "rebalance.need_assets_obs": {
        "cs": "Potřebuji alespoň 2 aktiva a dostatek pozorování (>=10).",
        "en": "At least 2 assets and enough observations (>=10) are required.",
    },
    "rebalance.need_assets_scenarios": {
        "cs": "Potřebuji alespoň 2 aktiva a dostatek scénářů (>=30).",
        "en": "At least 2 assets and enough scenarios (>=30) are required.",
    },
    "rebalance.active_portfolio_needs_tickers": {
        "cs": "Aktivní portfolio musí obsahovat alespoň 2 tickery pro rebalance.",
        "en": "The active portfolio needs at least 2 tickers for rebalance.",
    },
    "rebalance.optimization_failed": {
        "cs": "Optimalizace selhala: {error}",
        "en": "Optimization failed: {error}",
    },
    "rebalance.risk_parity_failed": {
        "cs": "Risk parity selhala: {error}",
        "en": "Risk parity failed: {error}",
    },
    "rebalance.cvar_failed": {
        "cs": "CVaR optimalizace selhala: {error}",
        "en": "CVaR optimization failed: {error}",
    },
    "rebalance.status_source": {
        "cs": "Zdroj dat: {source}",
        "en": "Data source: {source}",
    },
    "rebalance.status_source_text": {
        "cs": "tržní ceny aktivního portfolia z databáze",
        "en": "database-backed market prices for active portfolio",
    },
    "rebalance.status_mv_1": {
        "cs": "E[R] (annual) = {value}",
        "en": "E[R] (annual) = {value}",
    },
    "rebalance.status_mv_2": {
        "cs": "Vol (annual) = {vol} | Var (annual) = {var}",
        "en": "Vol (annual) = {vol} | Var (annual) = {var}",
    },
    "rebalance.status_mv_3": {
        "cs": "Gross exposure Σ|w| = {gross} | Net exposure Σw = {net}",
        "en": "Gross exposure Σ|w| = {gross} | Net exposure Σw = {net}",
    },
    "rebalance.status_mv_4": {
        "cs": "λ = {lam}, long-only = {long_only}, assets = {assets}",
        "en": "λ = {lam}, long-only = {long_only}, assets = {assets}",
    },
    "rebalance.status_rp_1": {
        "cs": "Vol (annual) = {vol}",
        "en": "Vol (annual) = {vol}",
    },
    "rebalance.status_rp_2": {
        "cs": "Gross Σ|w| = {gross} | Net Σw = {net}",
        "en": "Gross Σ|w| = {gross} | Net Σw = {net}",
    },
    "rebalance.status_rp_3": {
        "cs": "Long-only = {long_only}, assets = {assets}",
        "en": "Long-only = {long_only}, assets = {assets}",
    },
    "rebalance.status_cvar_1": {
        "cs": "α = {alpha}, long-only = {long_only}, assets = {assets}",
        "en": "α = {alpha}, long-only = {long_only}, assets = {assets}",
    },
    "rebalance.status_cvar_2": {
        "cs": "VaR (loss) ≈ {var} | CVaR/ES (loss) ≈ {cvar} (na periodu dat)",
        "en": "VaR (loss) ≈ {var} | CVaR/ES (loss) ≈ {cvar} (for the data period)",
    },
    "rebalance.status_cvar_3": {
        "cs": "Gross Σ|w| = {gross} | Net Σw = {net}",
        "en": "Gross Σ|w| = {gross} | Net Σw = {net}",
    },
    "common.true": {
        "cs": "ano",
        "en": "yes",
    },
    "common.false": {
        "cs": "ne",
        "en": "no",
    },
}


def normalize_language(language: str | None) -> str:
    if language in SUPPORTED_LANGUAGES:
        return str(language)
    return DEFAULT_LANGUAGE


def t(language: str | None, key: str, **kwargs: Any) -> str:
    lang = normalize_language(language)
    variants = TRANSLATIONS.get(key)
    if not variants:
        fallback = key
    else:
        fallback = variants.get(lang) or variants.get(DEFAULT_LANGUAGE) or key
    return fallback.format(**kwargs) if kwargs else fallback


def language_options(language: str | None) -> list[dict[str, str]]:
    return [
        {"label": "Čeština \U0001F1E8\U0001F1FF", "value": "cs"},
        {"label": "English \U0001F1EC\U0001F1E7", "value": "en"},
    ]


def bool_text(language: str | None, value: bool) -> str:
    return t(language, "common.true" if value else "common.false")
