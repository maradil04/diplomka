from dash import dcc, html, page_container

from components.auth_controls import build_auth_controls
from components.portfolio_sidebar import build_portfolio_sidebar


def _build_nav_links(authenticated):
    if not authenticated:
        return []
    return [
        dcc.Link("Dashboard", href="/dashboard", className="shell-nav-link"),
        dcc.Link("Predikce", href="/predikce", className="shell-nav-link"),
        dcc.Link("Rebalance", href="/rebalance", className="shell-nav-link"),
    ]


def build_app_shell(*, pathname, auth_data, portfolios, active_portfolio_id, ui_data):
    authenticated = bool(auth_data and auth_data.get("authenticated"))
    sidebar_open = bool((ui_data or {}).get("portfolio_sidebar_open"))
    portfolio_options = [{"label": item["name"], "value": item["id"]} for item in portfolios]

    nav_children = _build_nav_links(authenticated)
    auth_controls = build_auth_controls(auth_data)

    content_style = {
        "paddingRight": "24px",
        "paddingLeft": "24px",
        "paddingTop": "88px",
    }

    header = html.Header(
        className="shell-header",
        style={
            "position": "fixed",
            "top": 0,
            "left": 0,
            "right": 0,
            "height": "72px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            "padding": "0 24px",
            "background": "#141414",
            "borderBottom": "1px solid rgba(255,255,255,0.12)",
            "zIndex": 1100,
        },
        children=[
            html.Div(nav_children, className="shell-nav", style={"display": "flex", "alignItems": "center"}),
            html.Div(
                auth_controls,
                id="shell-auth-center",
                style={
                    "position": "absolute",
                    "left": "50%",
                    "transform": "translateX(-50%)",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "maxWidth": "50%",
                },
            ),
            html.Div(style={"width": "140px"}),
        ],
    )

    sidebar = build_portfolio_sidebar(portfolio_options, active_portfolio_id, sidebar_open)
    sidebar_toggle = html.Button(
        id="sidebar-toggle",
        n_clicks=0,
        className="shell-sidebar-toggle",
        style={
            "position": "fixed",
            "top": "16px",
            "right": "20px",
            "zIndex": 1400,
            "height": "42px",
            "padding": "0 14px",
            "display": "flex" if authenticated else "none",
            "alignItems": "center",
            "gap": "10px",
            "border": "1px solid rgba(255,255,255,0.18)",
            "background": "rgba(0,0,0,0.9)",
            "color": "white",
            "cursor": "pointer",
            "borderRadius": "10px",
        },
        children=[
            html.Span(
                "‹" if sidebar_open else "›",
                id="sidebar-toggle-arrow",
                style={"fontSize": "20px", "lineHeight": "1", "width": "14px", "textAlign": "center"},
            ),
            html.Span("Portfolio"),
        ],
    )
    return html.Div(
        children=[
            header,
            sidebar_toggle,
            sidebar,
            html.Main(page_container, style=content_style),
        ]
    )
