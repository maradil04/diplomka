from datetime import date

from dash import dcc, html


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


def _portfolio_rows(portfolios, active_portfolio_id):
    if not portfolios:
        return [html.Div("No portfolios yet.", className="portfolio-empty")]

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


def build_portfolio_sidebar(portfolios, active_portfolio_id, is_open):
    has_portfolios = bool(portfolios)

    return html.Div(
        id="portfolio-sidebar",
        style=_sidebar_style(is_open),
        children=[
            html.Div(
                id="portfolio-sidebar-content",
                style={"opacity": "1"},
                children=[
                    html.H3("Portfolios"),
                    html.P("Global portfolio context for dashboard, prediction, and rebalance."),
                    html.Div(
                        style={"marginTop": "16px"},
                        children=[
                            dcc.DatePickerSingle(
                                id="vyber-datum",
                                date=date.today(),
                                display_format="DD.MM.YYYY",
                                placeholder="Vyber datum",
                                className="date-picker sidebar-date-picker",
                                style={"background": "transparent", "width": "100%"},
                            ),
                        ],
                    ),
                    html.Div(
                        style={"marginTop": "12px"},
                        children=[
                            dcc.Upload(
                                id="upload-data",
                                children=html.Button("Nahrat CSV", className="upload-button sidebar-upload-button", style={"width": "100%"}),
                                multiple=False,
                            )
                        ],
                    ),
                    html.Div(
                        id="upload-status",
                        style={"marginTop": "10px", "fontSize": "14px", "opacity": "0.85"},
                    ),
                    html.Div(
                        style={"display": "flex", "gap": "8px", "marginTop": "16px"},
                        children=[
                            dcc.Input(
                                id="portfolio-create-name",
                                type="text",
                                placeholder="New portfolio name",
                                style={"flex": "1"},
                            ),
                            html.Button("Create", id="portfolio-create-button", n_clicks=0),
                        ],
                    ),
                    html.Div(
                        id="portfolio-list",
                        className="portfolio-list",
                        children=_portfolio_rows(portfolios, active_portfolio_id),
                        style={"marginTop": "16px"},
                    ),
                    html.Div(
                        id="portfolio-sidebar-status",
                        children="No portfolios yet." if not has_portfolios else "Active portfolio drives all analysis pages.",
                        style={"marginTop": "16px", "fontSize": "14px", "opacity": "0.8"},
                    ),
                ],
            )
        ],
    )
