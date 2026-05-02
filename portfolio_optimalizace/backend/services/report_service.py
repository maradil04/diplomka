from __future__ import annotations

from io import BytesIO
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

from backend.repositories.portfolios import get_portfolio_for_user
from backend.services.market_data_service import load_market_data
from backend.services.portfolio_service import empty_transactions_dataframe, load_portfolio_transactions_dataframe
from utils.portfolio_history import build_portfolio_value_history, portfolio_tickers


REPORT_COLORS = {
    "green": "#00a17b",
    "green_soft": "#dff7ef",
    "green_mid": "#8adfc5",
    "dark": "#12352c",
    "text": "#1f2a26",
    "muted": "#5d6e68",
    "grid": "#d7e4de",
    "border": "#c8d9d2",
    "panel": "#f7fbf9",
    "header": "#e8f4ef",
    "accent": "#f27a1a",
    "warning": "#ffd37a",
}

A4_FIGSIZE = (8.27, 11.69)
REPORT_WATERMARK = "Martin Radil - Diplomov\u00e1 pr\u00e1ce"
FOOTER_LINE_Y = 0.032
FOOTER_SAFE_TOP_Y = 0.06
CONTENT_BOTTOM_Y = 0.09
CHART_PAGE_BOTTOM_Y = 0.15


def _style_report_panel(ax, title: str) -> None:
    ax.set_facecolor("white")
    ax.add_patch(
        Rectangle(
            (0.0, 0.0),
            1.0,
            1.0,
            transform=ax.transAxes,
            facecolor=REPORT_COLORS["panel"],
            edgecolor=REPORT_COLORS["border"],
            linewidth=1.0,
            zorder=-20,
        )
    )
    ax.add_patch(
        Rectangle(
            (0.0, 0.90),
            1.0,
            0.10,
            transform=ax.transAxes,
            facecolor=REPORT_COLORS["header"],
            edgecolor=REPORT_COLORS["border"],
            linewidth=1.0,
            zorder=-10,
        )
    )
    ax.text(
        0.02,
        0.945,
        title,
        transform=ax.transAxes,
        ha="left",
        va="center",
        fontsize=12,
        fontweight="bold",
        color=REPORT_COLORS["dark"],
    )


def _style_chart_axes(ax) -> None:
    for spine in ax.spines.values():
        spine.set_color(REPORT_COLORS["border"])
        spine.set_linewidth(1.0)


def _reserve_chart_header_space(ax) -> None:
    box = ax.get_position()
    ax.set_position([box.x0, box.y0, box.width, box.height * 0.88])


def _style_chart_panel(ax, title: str) -> None:
    ax.set_facecolor("white")
    ax.add_patch(
        Rectangle(
            (0.0, 0.0),
            1.0,
            1.0,
            transform=ax.transAxes,
            facecolor=REPORT_COLORS["panel"],
            edgecolor=REPORT_COLORS["border"],
            linewidth=1.0,
            zorder=-20,
        )
    )
    ax.set_title(title, fontsize=12, fontweight="bold", color=REPORT_COLORS["dark"], pad=1)


def _save_pdf_page(pdf, fig) -> None:
    page_number = pdf.get_pagecount() + 1
    fig.add_artist(plt.Line2D([0.05, 0.95], [FOOTER_LINE_Y, FOOTER_LINE_Y], transform=fig.transFigure, color=REPORT_COLORS["border"], linewidth=0.8))
    if page_number > 1:
        fig.text(
            0.50,
            0.015,
            str(page_number),
            ha="center",
            va="bottom",
            fontsize=8,
            color=REPORT_COLORS["muted"],
            alpha=0.95,
        )
    fig.text(
        0.985,
        0.018,
        REPORT_WATERMARK,
        ha="right",
        va="bottom",
        fontsize=8,
        color=REPORT_COLORS["muted"],
        alpha=0.9,
    )
    pdf.savefig(fig)


def generate_portfolio_report_pdf(*, user_id: int, portfolio_id: int, report_date=None) -> tuple[bytes, str]:
    portfolio = get_portfolio_for_user(user_id, portfolio_id)
    if not portfolio:
        raise ValueError("Active portfolio was not found.")

    dataframe = load_portfolio_transactions_dataframe(user_id, portfolio_id, fallback=empty_transactions_dataframe())
    if dataframe.empty or "Type" not in dataframe.columns:
        raise ValueError("The active portfolio has no data to export.")

    import pages.home as home
    import pages.predikce as pred

    target_date = home._to_naive_ts(report_date) if report_date else pd.Timestamp.utcnow().normalize()
    active_portfolio_data = {"portfolio_id": portfolio_id}
    tickers = sorted(set(portfolio_tickers(dataframe)))
    prices = load_market_data(tickers=tickers, use_cache=False).copy() if tickers else pd.DataFrame()
    if not prices.empty and "Ticker_clean" not in prices.columns and "Ticker" in prices.columns:
        prices["Ticker_clean"] = prices["Ticker"].astype(str).str.split(".").str[0]

    summary_metrics = home._resolve_summary_metrics(target_date, dataframe, active_portfolio_data)
    free_capital = float(home.vypocitat_nevyuzity_kapital(target_date, dataframe))
    holdings_df = _build_holdings_table(home, target_date, dataframe, prices)
    asset_risk_df = _build_asset_risk_table(home, report_date, dataframe, prices)
    portfolio_history_df = _build_portfolio_history(home, report_date, dataframe, prices)
    allocation_df = _build_allocation_table(home, target_date, dataframe)
    fees_df = _build_fees_table(home, target_date, dataframe)
    monthly_dividends_df = _build_monthly_dividends_table(home, dataframe)
    prediction_payload = _build_portfolio_prediction(pred, dataframe, prices)

    buffer = BytesIO()
    with PdfPages(buffer) as pdf:
        _add_cover_page(
            pdf,
            portfolio_name=portfolio["name"],
            report_date=target_date,
            ticker_count=len(tickers),
            row_count=len(dataframe),
        )
        _add_summary_page(pdf, portfolio["name"], target_date, summary_metrics, free_capital)
        _add_compact_table_pages(
            pdf,
            [
                ("Portfolio Holdings", holdings_df),
                ("Asset Risk Metrics", asset_risk_df),
            ],
        )

        chart_specs = []
        if not allocation_df.empty:
            chart_specs.append(("barh", "Portfolio Allocation", allocation_df))
        if not fees_df.empty and fees_df["Total_money"].abs().sum() > 0:
            chart_specs.append(("fees", "Passive Income And Expenses", fees_df))
        if not monthly_dividends_df.empty and monthly_dividends_df["Total_clean"].abs().sum() > 0:
            chart_specs.append(("monthly", "Monthly Dividends", monthly_dividends_df))
        if not portfolio_history_df.empty:
            chart_specs.append(("history", "Portfolio Value History", portfolio_history_df))
        if prediction_payload is not None:
            chart_specs.append(("prediction", "Portfolio Prediction", prediction_payload))

        _add_compact_chart_pages(pdf, chart_specs)

        if prediction_payload is None:
            _add_note_page(
                pdf,
                "Portfolio Prediction",
                ["Prediction could not be generated for this portfolio with the currently available data."],
            )

    filename = _safe_report_filename(portfolio["name"], target_date)
    return buffer.getvalue(), filename


def _safe_report_filename(portfolio_name: str, report_date) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", str(portfolio_name or "portfolio")).strip("_") or "portfolio"
    return f"{clean}_report_{pd.Timestamp(report_date).strftime('%Y-%m-%d')}.pdf"


def _build_holdings_table(home, target_date, dataframe: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()

    result_df = home.sjednoceni(target_date, dataframe)
    result_price = home.soucasna_cena(target_date, prices)
    result_divi = home.vypocet_dividend(target_date, dataframe)
    if result_df.empty:
        return pd.DataFrame()

    result_df["Avg_purch_price"] = (result_df["Total_value"] / result_df["Total_quantity"]).replace([np.inf, -np.inf], np.nan)
    result_df["Ticker_clean"] = result_df["Ticker"].astype(str).str.split(".").str[0]
    if not result_divi.empty:
        result_divi["Ticker_clean"] = result_divi["Ticker"].astype(str).str.split(".").str[0]
        result_df = pd.merge(result_df, result_divi[["Ticker_clean", "Total_money"]], on="Ticker_clean", how="left")
    else:
        result_df["Total_money"] = 0.0

    final_df = pd.merge(result_df, result_price, on="Ticker_clean", how="left")
    final_df["Total_curr_val"] = (pd.to_numeric(final_df["Total_quantity"], errors="coerce") * pd.to_numeric(final_df["adjusted_close"], errors="coerce")).round(2)
    final_df["Total_purch_val"] = pd.to_numeric(final_df["Total_value"], errors="coerce").round(2)
    final_df["Dividends"] = pd.to_numeric(final_df["Total_money"], errors="coerce").fillna(0.0).round(2)
    final_df["Profit"] = (final_df["Total_curr_val"] - final_df["Total_purch_val"] + final_df["Dividends"]).round(2)
    final_df["Avg_purch_price"] = pd.to_numeric(final_df["Avg_purch_price"], errors="coerce").round(2)
    final_df["Total_quantity"] = pd.to_numeric(final_df["Total_quantity"], errors="coerce").round(4)
    return final_df[
        ["Ticker", "Total_purch_val", "Total_curr_val", "Total_quantity", "Avg_purch_price", "Dividends", "Profit"]
    ].rename(
        columns={
            "Ticker": "Ticker",
            "Total_purch_val": "Purchased Value",
            "Total_curr_val": "Current Value",
            "Total_quantity": "Quantity",
            "Avg_purch_price": "Average Purchase Price",
            "Dividends": "Dividends",
            "Profit": "Profit",
        }
    )


def _build_asset_risk_table(home, selected_date, dataframe: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(columns=["Ticker", "Volatility", "Sharpe Ratio", "Sortino Ratio"])

    tickers = set(portfolio_tickers(dataframe))
    prices = prices.query("Ticker_clean in @tickers").copy()
    target_date = home._force_naive_scalar(selected_date)
    prices["date"] = home._to_naive_day(prices["date"])
    prices = prices.query("date <= @target_date")
    prices["Return"] = prices.groupby("Ticker_clean")["adjusted_close"].pct_change()
    risk_free_rate = 0.042

    rows = []
    for ticker, group in prices.groupby("Ticker_clean"):
        returns = group["Return"].dropna()
        if returns.empty:
            continue
        mean_return = returns.mean()
        std_return = returns.std()
        annual_return = mean_return * 252
        annual_volatility = std_return * np.sqrt(252)
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility else 0.0
        downside_returns = returns[returns < (risk_free_rate / 252)]
        downside_deviation = downside_returns.std()
        annual_downside_deviation = downside_deviation * np.sqrt(252)
        sortino_ratio = (annual_return - risk_free_rate) / annual_downside_deviation if annual_downside_deviation else 0.0
        rows.append(
            {
                "Ticker": ticker,
                "Volatility": round(std_return, 6),
                "Sharpe Ratio": round(sharpe_ratio, 6),
                "Sortino Ratio": round(sortino_ratio, 6),
            }
        )
    return pd.DataFrame(rows).sort_values("Ticker") if rows else pd.DataFrame(columns=["Ticker", "Volatility", "Sharpe Ratio", "Sortino Ratio"])


def _build_portfolio_history(home, selected_date, dataframe: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])
    tickers = set(portfolio_tickers(dataframe))
    filtered_prices = prices.query("Ticker_clean in @tickers")
    target_date = home._force_naive_scalar(selected_date)
    result_df = home.hodnota_portfolia_v_case(target_date, dataframe, filtered_prices)
    if result_df.empty:
        return result_df
    plot_df = result_df.copy().sort_values("date")
    plot_df = plot_df.dropna(subset=["portfolio_value"])
    return plot_df[plot_df["portfolio_value"] > 0]


def _build_allocation_table(home, target_date, dataframe: pd.DataFrame) -> pd.DataFrame:
    result_df = home.sjednoceni(target_date, dataframe)
    if result_df.empty:
        return pd.DataFrame(columns=["Ticker", "Total_value"])
    return result_df.sort_values("Total_value", ascending=False)[["Ticker", "Total_value"]]


def _build_fees_table(home, target_date, dataframe: pd.DataFrame) -> pd.DataFrame:
    result_df = home.fees_divi(target_date, dataframe)
    return result_df.sort_values("Total_money", ascending=False) if not result_df.empty else pd.DataFrame(columns=["Type", "Total_money"])


def _build_monthly_dividends_table(home, dataframe: pd.DataFrame) -> pd.DataFrame:
    required = {"Type", "Date", "Total Amount"}
    if dataframe.empty or not required.issubset(set(dataframe.columns)):
        return pd.DataFrame(columns=["month", "Total_clean"])

    all_dates = pd.to_datetime(dataframe["Date"], errors="coerce", utc=True).dt.tz_convert(None).dropna()
    if all_dates.empty:
        return pd.DataFrame(columns=["month", "Total_clean"])

    month_start = all_dates.min().to_period("M").to_timestamp()
    month_end = all_dates.max().to_period("M").to_timestamp()
    full_months = pd.DataFrame({"month": pd.date_range(month_start, month_end, freq="MS")})

    div = dataframe[dataframe["Type"].astype(str).str.contains("DIVIDEND", na=False)].copy()
    if div.empty:
        return pd.DataFrame(columns=["month", "Total_clean"])

    div["Date"] = pd.to_datetime(div["Date"], errors="coerce", utc=True).dt.tz_convert(None)
    div["Total_clean"] = home._parse_money_series(div["Total Amount"])
    div = div.dropna(subset=["Date", "Total_clean"])
    if div.empty:
        return pd.DataFrame(columns=["month", "Total_clean"])

    div["month"] = div["Date"].dt.to_period("M").dt.to_timestamp()
    monthly = div.groupby("month", as_index=False)["Total_clean"].sum().sort_values("month")
    return full_months.merge(monthly, on="month", how="left").fillna({"Total_clean": 0.0})


def _build_portfolio_prediction(pred, dataframe: pd.DataFrame, prices: pd.DataFrame):
    if dataframe.empty or "Ticker" not in dataframe.columns or prices.empty:
        return None

    tickers_clean = dataframe["Ticker"].astype(str).str.split(".").str[0].dropna().unique().tolist()
    prices_filtered = prices[prices["Ticker_clean"].isin(tickers_clean)].copy()
    if prices_filtered.empty:
        return None

    portfolio_twr = pred.build_portfolio_twr_index(dataframe, prices_filtered, base=100.0)
    if portfolio_twr.empty or "twr_index" not in portfolio_twr.columns:
        return None

    performance_series = (
        portfolio_twr[["date", "twr_index"]]
        .dropna(subset=["date", "twr_index"])
        .drop_duplicates(subset=["date"])
        .sort_values("date")
        .set_index("date")["twr_index"]
        .astype(float)
    )
    performance_series = performance_series[performance_series > 0].dropna().asfreq("B").ffill()
    if len(performance_series) < 80:
        return None

    current_value_series = (
        portfolio_twr[["date", "portfolio_value"]]
        .dropna(subset=["date", "portfolio_value"])
        .drop_duplicates(subset=["date"])
        .sort_values("date")
        .set_index("date")["portfolio_value"]
        .astype(float)
    )
    current_value_series = current_value_series[current_value_series > 0].dropna().asfreq("B").ffill()

    log_ret = np.log(performance_series).diff().dropna()
    if len(log_ret) < 80:
        return None

    mean_model, mean_label, mean_rmse, _season_period = pred.pick_mean_model_rmse(log_ret)
    if mean_model is None:
        return None

    future_index = pred.make_future_index(performance_series.index, 30)
    future_mean_lr = pd.Series(mean_model.forecast(steps=30).values, index=future_index, name="mu_lr")
    resid = pd.Series(getattr(mean_model, "resid", None))
    if resid is None or resid.empty:
        fitted = pd.Series(getattr(mean_model, "fittedvalues", None))
        if fitted is not None and not fitted.empty:
            aligned = log_ret.iloc[-len(fitted):]
            resid = pd.Series(aligned.values - fitted.values)
        else:
            resid = log_ret - log_ret.mean()

    sigma_future, garch_label, garch_rmse, arch_p, _arch_stat = pred.forecast_sigma_series(resid, future_index, 30)
    last_index_level = float(performance_series.iloc[-1])
    current_portfolio_value = float(current_value_series.iloc[-1])
    pred_index = pred.returns_to_price_path(last_index_level, future_mean_lr)
    if sigma_future.isna().all():
        hist_sigma = float(log_ret.std(ddof=1))
        sigma_future = pd.Series(np.full(30, hist_sigma), index=future_index, name="sigma")

    lower1_index, upper1_index = pred.sigma_to_price_bands(last_index_level, future_mean_lr, sigma_future, k=1.0)
    lower2_index, upper2_index = pred.sigma_to_price_bands(last_index_level, future_mean_lr, sigma_future, k=2.0)
    scale = current_portfolio_value / max(last_index_level, 1e-12)
    price_pred = pred_index * scale
    lower1, upper1 = lower1_index * scale, upper1_index * scale
    lower2, upper2 = lower2_index * scale, upper2_index * scale
    return {
        "history": current_value_series,
        "forecast": price_pred,
        "lower1": lower1,
        "upper1": upper1,
        "lower2": lower2,
        "upper2": upper2,
        "mean_label": f"{mean_label} on cash-flow-adjusted returns",
        "mean_rmse": mean_rmse,
        "garch_label": garch_label,
        "garch_rmse": garch_rmse,
        "arch_p": arch_p,
    }


def _add_cover_page(pdf, *, portfolio_name: str, report_date, ticker_count: int, row_count: int) -> None:
    fig, ax = plt.subplots(figsize=A4_FIGSIZE)
    ax.axis("off")
    ax.add_patch(Rectangle((0.035, FOOTER_SAFE_TOP_Y), 0.93, 0.90, transform=ax.transAxes, facecolor=REPORT_COLORS["panel"], edgecolor=REPORT_COLORS["border"], linewidth=1.4))
    ax.add_patch(Rectangle((0.035, 0.80), 0.93, 0.16, transform=ax.transAxes, facecolor=REPORT_COLORS["green"], edgecolor=REPORT_COLORS["green"], linewidth=0))
    ax.text(0.08, 0.875, "PORTFOLIO REPORT", ha="left", va="center", fontsize=24, fontweight="bold", color="white")
    ax.text(0.08, 0.705, portfolio_name, ha="left", va="center", fontsize=20, fontweight="bold", color=REPORT_COLORS["dark"])
    ax.text(0.08, 0.625, f"Report date: {pd.Timestamp(report_date).strftime('%Y-%m-%d')}", ha="left", va="center", fontsize=12, color=REPORT_COLORS["text"])
    ax.text(0.08, 0.57, f"Tracked tickers: {ticker_count}", ha="left", va="center", fontsize=12, color=REPORT_COLORS["text"])
    ax.text(0.08, 0.515, f"Imported transactions: {row_count}", ha="left", va="center", fontsize=12, color=REPORT_COLORS["text"])
    ax.text(0.08, 0.13, "Generated from the active portfolio and current prediction model.", ha="left", va="center", fontsize=10, color=REPORT_COLORS["muted"])
    _save_pdf_page(pdf, fig)
    plt.close(fig)


def _add_summary_page(pdf, portfolio_name: str, report_date, metrics: dict, free_capital: float) -> None:
    fig, axes = plt.subplots(2, 1, figsize=A4_FIGSIZE, gridspec_kw={"height_ratios": [1.2, 0.95]})
    fig.suptitle(f"Portfolio Summary: {portfolio_name}", fontsize=17, fontweight="bold", y=0.97)
    for ax in axes:
        ax.axis("off")

    summary_df = pd.DataFrame(
        [
            ["Portfolio value", f"{metrics['portfolio_value_total']:.2f} EUR"],
            ["Invested capital", f"{metrics['invested_total']:.2f} EUR"],
            ["Total profit", f"{metrics['total_profit']:.2f} EUR"],
            ["ROI", f"{metrics['roi']:.2f}%"],
            ["Estimated free cash", f"{free_capital:.2f} EUR"],
            ["As of", pd.Timestamp(report_date).strftime("%Y-%m-%d")],
        ],
        columns=["Metric", "Value"],
    )
    risk_df = pd.DataFrame(
        [
            ["Annualized return", f"{metrics['annualized_return']:.2f}%"],
            ["Max drawdown", f"{metrics['max_drawdown']:.2f}%"],
            ["Portfolio volatility", f"{metrics['portfolio_volatility']:.2f}%"],
        ],
        columns=["Risk metric", "Value"],
    )

    _draw_table(axes[0], summary_df, title="Dashboard Summary", font_size=9, y_scale=1.15)
    _draw_table(axes[1], risk_df, title="Portfolio Risk Summary", font_size=9, y_scale=1.15)
    fig.subplots_adjust(top=0.93, hspace=0.12, left=0.06, right=0.94, bottom=CONTENT_BOTTOM_Y)
    _save_pdf_page(pdf, fig)
    plt.close(fig)


def _add_compact_table_pages(pdf, sections: list[tuple[str, pd.DataFrame]], rows_per_page: int = 18) -> None:
    prepared = []
    for title, dataframe in sections:
        if dataframe is None or dataframe.empty:
            continue
        chunks = [dataframe.iloc[index:index + rows_per_page] for index in range(0, len(dataframe), rows_per_page)]
        for idx, chunk in enumerate(chunks, start=1):
            page_title = title if len(chunks) == 1 else f"{title} ({idx}/{len(chunks)})"
            prepared.append((page_title, chunk))

    if not prepared:
        return

    for start in range(0, len(prepared), 2):
        page_sections = prepared[start:start + 2]
        fig, axes = plt.subplots(len(page_sections), 1, figsize=A4_FIGSIZE)
        if len(page_sections) == 1:
            axes = [axes]
        for ax, (title, chunk) in zip(axes, page_sections):
            ax.axis("off")
            _draw_table(ax, chunk, title=title, font_size=7.6, y_scale=1.02)
        fig.subplots_adjust(top=0.955, hspace=0.18, left=0.04, right=0.96, bottom=CONTENT_BOTTOM_Y)
        _save_pdf_page(pdf, fig)
        plt.close(fig)


def _draw_table(ax, dataframe: pd.DataFrame, title: str, *, font_size: float = 8.5, y_scale: float = 1.12) -> None:
    _style_report_panel(ax, title)
    display_df = dataframe.copy()
    for column in display_df.columns:
        if pd.api.types.is_numeric_dtype(display_df[column]):
            display_df[column] = display_df[column].map(lambda value: f"{value:.4f}" if isinstance(value, float) else str(value))
        else:
            display_df[column] = display_df[column].astype(str)
    table = ax.table(
        cellText=display_df.values,
        colLabels=display_df.columns,
        loc="upper center",
        cellLoc="left",
        colLoc="left",
        bbox=[0.02, 0.04, 0.96, 0.84],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(font_size)
    table.scale(1, y_scale)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(REPORT_COLORS["border"])
        cell.set_linewidth(0.7)
        if row == 0:
            cell.set_facecolor(REPORT_COLORS["header"])
            cell.get_text().set_fontweight("bold")
            cell.get_text().set_color(REPORT_COLORS["dark"])
        else:
            cell.set_facecolor("white" if row % 2 == 1 else REPORT_COLORS["panel"])
            cell.get_text().set_color(REPORT_COLORS["text"])


def _add_compact_chart_pages(pdf, chart_specs: list[tuple[str, str, object]]) -> None:
    if not chart_specs:
        return

    for start in range(0, len(chart_specs), 2):
        page_specs = chart_specs[start:start + 2]
        fig, axes = plt.subplots(len(page_specs), 1, figsize=A4_FIGSIZE)
        if len(page_specs) == 1:
            axes = [axes]
        for ax, (kind, title, payload) in zip(axes, page_specs):
            if kind == "barh":
                _draw_horizontal_bar_chart(ax, title, payload["Ticker"], payload["Total_value"], x_label="Purchased value", value_format="{:.2f}")
            elif kind == "fees":
                _draw_horizontal_bar_chart(ax, title, payload["Type"], payload["Total_money"], x_label="Amount", value_format="{:.2f}", rotate_y_labels=True)
            elif kind == "monthly":
                _draw_monthly_dividend_chart(ax, payload, title)
            elif kind == "history":
                _draw_portfolio_history_chart(ax, payload, title)
            elif kind == "prediction":
                _draw_prediction_chart(ax, payload, title)
        fig.subplots_adjust(top=0.955, hspace=0.40, left=0.08, right=0.97, bottom=CHART_PAGE_BOTTOM_Y)
        _save_pdf_page(pdf, fig)
        plt.close(fig)


def _add_horizontal_bar_page(pdf, title: str, labels, values, *, x_label: str, value_format: str) -> None:
    fig, ax = plt.subplots(figsize=A4_FIGSIZE)
    _draw_horizontal_bar_chart(ax, title, labels, values, x_label=x_label, value_format=value_format)
    fig.subplots_adjust(top=0.95, left=0.08, right=0.97, bottom=CHART_PAGE_BOTTOM_Y)
    _save_pdf_page(pdf, fig)
    plt.close(fig)


def _draw_horizontal_bar_chart(ax, title: str, labels, values, *, x_label: str, value_format: str, rotate_y_labels: bool = False) -> None:
    _style_chart_panel(ax, title)
    labels = list(labels)
    values = pd.to_numeric(pd.Series(values), errors="coerce").fillna(0.0)
    order = np.arange(len(labels))
    ax.barh(order, values.values, color=REPORT_COLORS["green"], edgecolor=REPORT_COLORS["dark"], linewidth=0.4)
    ax.set_yticks(order)
    ax.set_yticklabels(labels, fontsize=8, color=REPORT_COLORS["text"], rotation=90 if rotate_y_labels else 0, va="center")
    ax.invert_yaxis()
    ax.set_xlabel(x_label, fontsize=9, color=REPORT_COLORS["text"])
    ax.tick_params(axis="x", labelsize=8, colors=REPORT_COLORS["muted"])
    for idx, value in enumerate(values.values):
        ax.text(value, idx, f" {value_format.format(value)}", va="center", fontsize=7, color=REPORT_COLORS["text"])
    ax.grid(axis="x", color=REPORT_COLORS["grid"], alpha=1.0, linewidth=0.8)
    _style_chart_axes(ax)
    if rotate_y_labels:
        ax.tick_params(axis="y", pad=14)


def _add_monthly_dividend_page(pdf, monthly_df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=A4_FIGSIZE)
    _draw_monthly_dividend_chart(ax, monthly_df, "Monthly Dividends")
    fig.subplots_adjust(top=0.95, left=0.08, right=0.97, bottom=CHART_PAGE_BOTTOM_Y)
    _save_pdf_page(pdf, fig)
    plt.close(fig)


def _add_portfolio_history_page(pdf, history_df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=A4_FIGSIZE)
    _draw_portfolio_history_chart(ax, history_df, "Portfolio Value History")
    fig.subplots_adjust(top=0.95, left=0.08, right=0.97, bottom=CHART_PAGE_BOTTOM_Y)
    _save_pdf_page(pdf, fig)
    plt.close(fig)


def _add_prediction_page(pdf, prediction_payload: dict) -> None:
    fig, ax = plt.subplots(figsize=A4_FIGSIZE)
    _draw_prediction_chart(ax, prediction_payload, "Portfolio Prediction")
    fig.subplots_adjust(top=0.95, left=0.08, right=0.97, bottom=CHART_PAGE_BOTTOM_Y)
    _save_pdf_page(pdf, fig)
    plt.close(fig)


def _draw_monthly_dividend_chart(ax, monthly_df: pd.DataFrame, title: str) -> None:
    _style_chart_panel(ax, title)
    ax.bar(monthly_df["month"], monthly_df["Total_clean"], color=REPORT_COLORS["green"], edgecolor=REPORT_COLORS["dark"], linewidth=0.4, width=18)
    ax.set_xlabel("Month", fontsize=9, color=REPORT_COLORS["text"])
    ax.set_ylabel("Amount", fontsize=9, color=REPORT_COLORS["text"])
    ax.tick_params(axis="both", labelsize=8, colors=REPORT_COLORS["muted"])
    ax.grid(axis="y", color=REPORT_COLORS["grid"], alpha=1.0, linewidth=0.8)
    _style_chart_axes(ax)
    ax.figure.autofmt_xdate()


def _draw_portfolio_history_chart(ax, history_df: pd.DataFrame, title: str) -> None:
    _style_chart_panel(ax, title)
    ax.plot(pd.to_datetime(history_df["date"]), history_df["portfolio_value"], color=REPORT_COLORS["green"], linewidth=1.8)
    ax.fill_between(pd.to_datetime(history_df["date"]), history_df["portfolio_value"], color=REPORT_COLORS["green_mid"], alpha=0.25)
    ax.set_xlabel("Date", fontsize=9, color=REPORT_COLORS["text"])
    ax.set_ylabel("Value (EUR)", fontsize=9, color=REPORT_COLORS["text"])
    ax.tick_params(axis="both", labelsize=8, colors=REPORT_COLORS["muted"])
    ax.grid(color=REPORT_COLORS["grid"], alpha=1.0, linewidth=0.8)
    _style_chart_axes(ax)
    ax.figure.autofmt_xdate()


def _draw_prediction_chart(ax, prediction_payload: dict, title: str) -> None:
    _style_chart_panel(ax, title)
    history = prediction_payload["history"]
    forecast = prediction_payload["forecast"]
    lower1 = prediction_payload["lower1"]
    upper1 = prediction_payload["upper1"]
    lower2 = prediction_payload["lower2"]
    upper2 = prediction_payload["upper2"]

    ax.plot(history.index, history.values, color=REPORT_COLORS["green"], linewidth=1.8, label="History")
    ax.plot(forecast.index, forecast.values, color=REPORT_COLORS["accent"], linewidth=1.8, linestyle="--", label="Forecast")
    ax.fill_between(lower2.index, lower2.values, upper2.values, color=REPORT_COLORS["warning"], alpha=0.14, label="+/-2 sigma")
    ax.fill_between(lower1.index, lower1.values, upper1.values, color=REPORT_COLORS["warning"], alpha=0.24, label="+/-1 sigma")
    ax.set_xlabel("Date", fontsize=9, color=REPORT_COLORS["text"])
    ax.set_ylabel("Portfolio value", fontsize=9, color=REPORT_COLORS["text"])
    ax.tick_params(axis="both", labelsize=8, colors=REPORT_COLORS["muted"])
    ax.grid(color=REPORT_COLORS["grid"], alpha=1.0, linewidth=0.8)
    _style_chart_axes(ax)
    legend = ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.985), ncol=2, fontsize=7, frameon=True)
    legend.get_frame().set_edgecolor(REPORT_COLORS["border"])
    legend.get_frame().set_facecolor("white")

    ax.figure.autofmt_xdate()


def _add_note_page(pdf, title: str, lines: list[str]) -> None:
    fig, ax = plt.subplots(figsize=A4_FIGSIZE)
    ax.axis("off")
    ax.set_title(title, fontsize=16, fontweight="bold", pad=20)
    y = 0.88
    for line in lines:
        ax.text(0.08, y, line, ha="left", va="top", fontsize=11)
        y -= 0.05
    _save_pdf_page(pdf, fig)
    plt.close(fig)
