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


def build_portfolio_sidebar(portfolio_options, active_portfolio_id, is_open):
    has_portfolios = bool(portfolio_options)

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
                    dcc.Dropdown(
                        id="portfolio-selector",
                        options=portfolio_options,
                        value=active_portfolio_id,
                        placeholder="Select portfolio",
                        disabled=not has_portfolios,
                        className="portfolio-selector",
                        style={"backgroundColor": "#0f0f0f", "color": "#00a17b"},
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
                        id="portfolio-sidebar-status",
                        children="No portfolios yet." if not has_portfolios else "Active portfolio drives all analysis pages.",
                        style={"marginTop": "16px", "fontSize": "14px", "opacity": "0.8"},
                    ),
                ],
            )
        ],
    )
