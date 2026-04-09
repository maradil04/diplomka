from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from app import app
from backend.services.portfolio_service import (
    create_user_portfolio,
    delete_user_portfolio,
    list_user_portfolios,
    load_portfolio_transactions_dataframe,
    resolve_active_portfolio,
    set_active_portfolio,
)
from backend.session import get_current_user
from components.app_shell import build_app_shell
from components.portfolio_sidebar import _sidebar_style


app.layout = html.Div(
    [
        dcc.Location(id="url"),
        dcc.Store(id="stored-data", storage_type="session"),
        dcc.Store(id="auth-store", storage_type="session"),
        dcc.Store(id="portfolio-list-store", storage_type="session"),
        dcc.Store(id="active-portfolio-store", storage_type="session"),
        dcc.Store(id="ui-store", storage_type="session", data={"portfolio_sidebar_open": False}),
        html.Div(id="route-guard-anchor", style={"display": "none"}),
        html.Div(
            id="app-shell",
            children=build_app_shell(
                pathname="/",
                auth_data={},
                portfolios=[],
                active_portfolio_id=None,
                ui_data={"portfolio_sidebar_open": False},
            ),
        ),
    ]
)


def _serialize_transactions(user, portfolio_state):
    if not user:
        return []
    portfolio_id = (portfolio_state or {}).get("portfolio_id") if isinstance(portfolio_state, dict) else None
    dataframe = load_portfolio_transactions_dataframe(user["id"], portfolio_id, fallback=None)
    if dataframe is None:
        return []
    return dataframe.to_dict("records")


def _serialize_auth(user):
    if not user:
        return {
            "authenticated": False,
            "user_id": None,
            "name": None,
            "email": None,
            "avatar_url": None,
        }
    return {
        "authenticated": True,
        "user_id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "avatar_url": user["avatar_url"],
    }


@callback(
    Output("auth-store", "data"),
    Output("portfolio-list-store", "data"),
    Output("active-portfolio-store", "data"),
    Input("url", "pathname"),
)
def hydrate_app_state(_pathname):
    user = get_current_user()
    auth_data = _serialize_auth(user)
    if not user:
        return auth_data, [], {"portfolio_id": None}

    active = resolve_active_portfolio(user["id"])
    portfolios = list_user_portfolios(user["id"])
    active_state = {"portfolio_id": active["id"] if active else None}
    return auth_data, portfolios, active_state


@callback(
    Output("stored-data", "data", allow_duplicate=True),
    Input("url", "pathname"),
    Input("active-portfolio-store", "data"),
    Input("auth-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def sync_dashboard_stored_data(pathname, active_portfolio_state, auth_data):
    if pathname != "/dashboard":
        return no_update
    if not (auth_data or {}).get("authenticated"):
        return []
    user = get_current_user()
    if not user:
        return []
    return _serialize_transactions(user, active_portfolio_state)


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input("url", "pathname"),
    Input("auth-store", "data"),
    prevent_initial_call=True,
)
def guard_client_routes(pathname, auth_data):
    protected = {"/dashboard", "/predikce", "/rebalance"}
    if pathname in protected and not (auth_data or {}).get("authenticated"):
        return "/"
    return no_update


@callback(
    Output("ui-store", "data"),
    Input("sidebar-toggle", "n_clicks"),
    State("ui-store", "data"),
    prevent_initial_call=True,
)
def toggle_sidebar(n_clicks, ui_data):
    if not n_clicks:
        return no_update
    current = dict(ui_data or {})
    current["portfolio_sidebar_open"] = not bool(current.get("portfolio_sidebar_open"))
    return current


@callback(
    Output("portfolio-list-store", "data", allow_duplicate=True),
    Output("active-portfolio-store", "data", allow_duplicate=True),
    Output("portfolio-sidebar-status", "children", allow_duplicate=True),
    Input({"type": "portfolio-select", "index": ALL}, "n_clicks"),
    Input({"type": "portfolio-delete", "index": ALL}, "n_clicks"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def handle_portfolio_actions(_select_clicks, _delete_clicks, auth_data):
    if not (auth_data or {}).get("authenticated"):
        return no_update, no_update, no_update

    user = get_current_user()
    if not user or not ctx.triggered_id:
        return no_update, no_update, no_update

    triggered = ctx.triggered_id
    portfolio_id = triggered.get("index") if isinstance(triggered, dict) else None
    if not portfolio_id:
        return no_update, no_update, no_update

    if triggered.get("type") == "portfolio-select":
        portfolio = set_active_portfolio(user["id"], portfolio_id)
        if not portfolio:
            return no_update, no_update, "Portfolio could not be selected."
        portfolios = list_user_portfolios(user["id"])
        return portfolios, {"portfolio_id": portfolio["id"]}, f"Active portfolio: {portfolio['name']}"

    if triggered.get("type") == "portfolio-delete":
        active, portfolios = delete_user_portfolio(user["id"], portfolio_id)
        if not active:
            return portfolios, {"portfolio_id": None}, "Portfolio deleted."
        return portfolios, {"portfolio_id": active["id"]}, f"Portfolio deleted. Active portfolio: {active['name']}"

    return no_update, no_update, no_update


@callback(
    Output("portfolio-list-store", "data", allow_duplicate=True),
    Output("active-portfolio-store", "data", allow_duplicate=True),
    Output("portfolio-create-name", "value"),
    Output("portfolio-sidebar-status", "children", allow_duplicate=True),
    Input("portfolio-create-button", "n_clicks"),
    State("portfolio-create-name", "value"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def create_portfolio_from_sidebar(n_clicks, portfolio_name, auth_data):
    if not n_clicks or not (auth_data or {}).get("authenticated"):
        return no_update, no_update, no_update, no_update

    user = get_current_user()
    if not user:
        return no_update, no_update, no_update, "Authentication required."

    portfolio = create_user_portfolio(user["id"], portfolio_name)
    portfolios = list_user_portfolios(user["id"])
    status = f"Created portfolio: {portfolio['name']}"
    return portfolios, {"portfolio_id": portfolio["id"]}, "", status


@callback(
    Output("app-shell", "children"),
    Input("url", "pathname"),
    Input("auth-store", "data"),
    Input("portfolio-list-store", "data"),
    Input("active-portfolio-store", "data"),
)
def render_shell(pathname, auth_data, portfolio_list, active_portfolio):
    return build_app_shell(
        pathname=pathname,
        auth_data=auth_data or {},
        portfolios=portfolio_list or [],
        active_portfolio_id=(active_portfolio or {}).get("portfolio_id"),
        ui_data={"portfolio_sidebar_open": False},
    )


@callback(
    Output("portfolio-sidebar", "style"),
    Output("sidebar-toggle-arrow", "children"),
    Output("sidebar-toggle", "style"),
    Input("ui-store", "data"),
    Input("auth-store", "data"),
    prevent_initial_call=False,
)
def sync_sidebar_ui(ui_data, auth_data):
    authenticated = bool((auth_data or {}).get("authenticated"))
    sidebar_open = bool((ui_data or {}).get("portfolio_sidebar_open"))
    sidebar_style = _sidebar_style(sidebar_open if authenticated else False)
    if not authenticated:
        sidebar_style["pointerEvents"] = "none"
        sidebar_style["opacity"] = "0"

    toggle_style = {
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
    }
    return sidebar_style, ("‹" if sidebar_open else "›"), toggle_style


if __name__ == "__main__":
    app.run(debug=True)
