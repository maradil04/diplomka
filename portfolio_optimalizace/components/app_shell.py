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
    menu_open = bool((ui_data or {}).get("menu_sidebar_open"))

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
            html.Button(
                id="menu-toggle",
                n_clicks=0,
                className="shell-menu-toggle",
                children=[html.Span("Menu")],
            ),
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

    mobile_menu = html.Div(
        id="mobile-menu-sidebar",
        className="mobile-menu-sidebar",
        style={
            "position": "fixed",
            "top": "0",
            "left": "0",
            "height": "100vh",
            "width": "300px",
            "maxWidth": "85vw",
            "overflowX": "hidden",
            "background": "#111",
            "color": "white",
            "padding": "24px",
            "borderRight": "1px solid rgba(255,255,255,0.15)",
            "transition": "transform 0.22s ease, opacity 0.22s ease",
            "transform": "translateX(0)" if menu_open else "translateX(-100%)",
            "opacity": "1" if menu_open else "0.96",
            "pointerEvents": "auto" if menu_open else "none",
            "zIndex": "1250",
            "boxSizing": "border-box",
        },
        children=[
            html.Div(
                className="mobile-menu-content",
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "18px"},
                        children=[
                            html.H3("Menu", style={"margin": 0}),
                            html.Button("Close", id="menu-close", n_clicks=0, className="portfolio-row-delete", style={"minWidth": "84px"}),
                        ],
                    ),
                    html.Div(nav_children, className="mobile-menu-nav"),
                    html.Div(auth_controls, className="mobile-menu-auth", style={"marginTop": "20px"}),
                ],
            )
        ],
    )

    sidebar = build_portfolio_sidebar(portfolios, active_portfolio_id, sidebar_open)
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
            mobile_menu,
            sidebar_toggle,
            sidebar,
            html.Main(page_container, style=content_style),
        ]
    )
