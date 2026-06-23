from datetime import date

from dash import dcc, html

from utils.i18n import language_options, normalize_language, t


def _sidebar_style(is_open):
    return {
        "position": "fixed",
        "top": "0",
        "right": "0",
        "height": "100vh",
        "width": "320px",
        "overflowX": "hidden",
        "background": "#111",
        "color": "white",
        "padding": "24px",
        "borderLeft": "1px solid rgba(255,255,255,0.15)",
        "transition": "transform 0.22s ease, opacity 0.22s ease",
        "transform": "translateX(0)" if is_open else "translateX(100%)",
        "opacity": "1" if is_open else "0.96",
        "pointerEvents": "auto" if is_open else "none",
        "zIndex": "1200",
        "boxSizing": "border-box",
    }


def _portfolio_rows(portfolios, active_portfolio_id, language):
    if not portfolios:
        return [html.Div(t(language, "sidebar.no_portfolios"), className="portfolio-empty")]

    rows = []
    for item in portfolios:
        portfolio_id = item["id"]
        is_active = portfolio_id == active_portfolio_id
        rows.append(
            html.Div(
                className=f"portfolio-row{' active' if is_active else ''}",
                children=[
                    html.Button(
                        item["name"],
                        id={"type": "portfolio-select", "index": portfolio_id},
                        n_clicks=0,
                        className="portfolio-row-select",
                    ),
                    html.Button(
                        "🗑",
                        id={"type": "portfolio-delete", "index": portfolio_id},
                        n_clicks=0,
                        className="portfolio-row-delete",
                    ),
                ],
            )
        )
    return rows


def build_portfolio_sidebar(portfolios, active_portfolio_id, is_open, language="cs"):
    lang = normalize_language(language)
    has_portfolios = bool(portfolios)

    return html.Div(
        id="portfolio-sidebar",
        style=_sidebar_style(is_open),
        children=[
            html.Div(
                id="portfolio-sidebar-content",
                style={"opacity": "1"},
                children=[
                    html.Div(
                        className="sidebar-language-block",
                        children=[
                            html.Label(t(lang, "sidebar.language"), className="sidebar-language-label"),
                            dcc.Dropdown(
                                id="language-switch",
                                options=language_options(lang),
                                value=lang,
                                clearable=False,
                                searchable=False,
                                className="sidebar-language-dropdown",
                            ),
                        ],
                    ),
                    html.H3(t(lang, "sidebar.portfolios")),
                    html.P(t(lang, "sidebar.context")),
                    html.Div(
                        style={"marginTop": "16px"},
                        children=[
                            dcc.DatePickerSingle(
                                id="vyber-datum",
                                date=date.today(),
                                display_format="DD.MM.YYYY",
                                placeholder=t(lang, "sidebar.select_date"),
                                className="date-picker sidebar-date-picker",
                                style={"background": "transparent", "width": "100%"},
                            ),
                        ],
                    ),
                    html.Div(
                        style={"marginTop": "12px"},
                        children=[
                            html.Details(
                                className="sidebar-import-details",
                                children=[
                                    html.Summary(t(lang, "sidebar.import_csv"), className="sidebar-import-summary"),
                                    html.Div(
                                        className="sidebar-import-panel",
                                        children=[
                                            html.P(
                                                t(lang, "sidebar.import_header"),
                                                style={"marginTop": "12px", "marginBottom": "8px"},
                                            ),
                                            html.Code(
                                                "Date, Ticker, Type, Quantity, Price per share, Total Amount, Currency",
                                                style={
                                                    "display": "block",
                                                    "whiteSpace": "normal",
                                                    "padding": "10px 12px",
                                                    "background": "rgba(255,255,255,0.06)",
                                                    "border": "1px solid rgba(255,255,255,0.12)",
                                                    "borderRadius": "8px",
                                                },
                                            ),
                                            html.P(
                                                t(lang, "sidebar.import_required"),
                                                style={"marginTop": "10px", "marginBottom": "8px", "fontSize": "13px", "opacity": "0.9"},
                                            ),
                                            html.P(
                                                t(lang, "sidebar.import_types"),
                                                style={"marginTop": "0", "marginBottom": "8px", "fontSize": "13px", "opacity": "0.9"},
                                            ),
                                            html.P(
                                                t(lang, "sidebar.import_note"),
                                                style={"marginTop": "0", "marginBottom": "12px", "fontSize": "13px", "opacity": "0.9"},
                                            ),
                                            dcc.Upload(
                                                id="upload-data",
                                                accept=".csv,text/csv",
                                                children=html.Button(
                                                    t(lang, "sidebar.choose_csv"),
                                                    className="upload-button sidebar-upload-button",
                                                    style={"width": "100%"},
                                                ),
                                                multiple=False,
                                            ),
                                        ],
                                    ),
                                ],
                            )
                        ],
                    ),
                    html.Div(
                        id="upload-status",
                        style={"marginTop": "10px", "fontSize": "14px", "opacity": "0.85"},
                    ),
                    html.Div(
                        style={"marginTop": "12px"},
                        children=[
                            html.Button(
                                t(lang, "sidebar.export_pdf"),
                                id="download-portfolio-report",
                                n_clicks=0,
                                className="sidebar-create-button",
                                style={"width": "100%"},
                            )
                        ],
                    ),
                    html.Div(
                        id="report-status",
                        style={"marginTop": "10px", "fontSize": "14px", "opacity": "0.85"},
                    ),
                    html.Div(
                        id="report-progress-wrapper",
                        className="report-progress-wrapper",
                        children=[
                            html.Div(id="report-progress-bar", className="report-progress-bar"),
                        ],
                    ),
                    html.Div(
                        className="sidebar-create-row",
                        children=[
                            dcc.Input(
                                id="portfolio-create-name",
                                type="text",
                                placeholder=t(lang, "sidebar.portfolio_name"),
                                className="sidebar-create-input",
                            ),
                            html.Button(t(lang, "sidebar.create"), id="portfolio-create-button", n_clicks=0, className="sidebar-create-button"),
                        ],
                    ),
                    html.Div(
                        id="portfolio-list",
                        className="portfolio-list",
                        children=_portfolio_rows(portfolios, active_portfolio_id, lang),
                        style={"marginTop": "16px"},
                    ),
                    html.Div(
                        id="portfolio-sidebar-status",
                        children=t(lang, "sidebar.no_portfolios") if not has_portfolios else t(lang, "sidebar.active_hint"),
                        style={"marginTop": "16px", "fontSize": "14px", "opacity": "0.8"},
                    ),
                ],
            )
        ],
    )
