import base64

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from app import app
from backend.services.portfolio_service import (
    create_user_portfolio,
    delete_user_portfolio,
    list_user_portfolios,
    load_portfolio_transactions_dataframe,
    resolve_active_portfolio,
    set_active_portfolio,
)
from backend.services.report_service import generate_portfolio_report_pdf
from backend.session import get_current_user
from components.app_shell import build_app_shell
from components.portfolio_sidebar import _sidebar_style
from pages import home, predikce, rebalance
from utils.i18n import normalize_language, t

server = app.server


app.layout = html.Div(
    [
        dcc.Location(id="url"),
        dcc.Store(id="stored-data", storage_type="session"),
        dcc.Store(id="auth-store", storage_type="session"),
        dcc.Store(id="portfolio-list-store", storage_type="session"),
        dcc.Store(id="active-portfolio-store", storage_type="session"),
        dcc.Store(id="language-store", storage_type="session", data="cs"),
        dcc.Store(id="ui-store", storage_type="session", data={"portfolio_sidebar_open": False, "menu_sidebar_open": False}),
        dcc.Download(id="portfolio-report-download"),
        dcc.Interval(id="auth-bootstrap", interval=0, n_intervals=0, max_intervals=1),
        dcc.Interval(id="active-portfolio-bootstrap", interval=0, n_intervals=0, max_intervals=1),
        html.Div(id="route-guard-anchor", style={"display": "none"}),
        html.Div(
            id="dashboard-empty-overlay",
            className="home-empty-state",
            style={"display": "none"},
            children=[
                html.Div(t("cs", "app.waiting_overlay"), id="dashboard-empty-overlay-text", className="home-empty-state-text"),
            ],
        ),
        html.Div(
            id="app-shell",
            children=build_app_shell(
                auth_data={},
                portfolios=[],
                active_portfolio_id=None,
                language="cs",
                ui_data={"portfolio_sidebar_open": False, "menu_sidebar_open": False},
            ),
        ),
    ]
)

app.validation_layout = html.Div([app.layout, home.layout, predikce.layout, rebalance.layout])


def _portfolio_id_from_state(portfolio_state):
    if not isinstance(portfolio_state, dict):
        return None
    portfolio_id = portfolio_state.get("portfolio_id")
    if portfolio_id in (None, ""):
        return None
    try:
        return int(portfolio_id)
    except (TypeError, ValueError):
        return None


def _serialize_transactions(user, portfolio_state):
    if not user:
        return []
    portfolio_id = _portfolio_id_from_state(portfolio_state)
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


@app.callback(
    Output("language-store", "data"),
    Input("language-switch", "value"),
    State("language-store", "data"),
    prevent_initial_call=True,
)
def sync_language(language_value, current_language):
    normalized = normalize_language(language_value)
    if normalized == normalize_language(current_language):
        return no_update
    return normalized


@app.callback(
    Output("dashboard-empty-overlay-text", "children"),
    Input("language-store", "data"),
)
def localize_overlay_text(language):
    return t(language, "app.waiting_overlay")


@app.callback(
    Output("auth-store", "data"),
    Output("portfolio-list-store", "data"),
    Input("auth-bootstrap", "n_intervals"),
)
def hydrate_auth_and_portfolios(_n_intervals):
    user = get_current_user()
    auth_data = _serialize_auth(user)
    if not user:
        return auth_data, []

    portfolios = list_user_portfolios(user["id"])
    return auth_data, portfolios


@app.callback(
    Output("active-portfolio-store", "data"),
    Input("active-portfolio-bootstrap", "n_intervals"),
    State("active-portfolio-store", "data"),
)
def ensure_active_portfolio(_n_intervals, current_active_portfolio):
    current_portfolio_id = _portfolio_id_from_state(current_active_portfolio)
    if current_portfolio_id:
        return no_update

    user = get_current_user()
    if not user:
        return {"portfolio_id": None}

    active = resolve_active_portfolio(user["id"])
    return {"portfolio_id": active["id"] if active else None}


@app.callback(
    Output("stored-data", "data", allow_duplicate=True),
    Input("active-portfolio-store", "data"),
    State("auth-store", "data"),
    State("url", "pathname"),
    prevent_initial_call="initial_duplicate",
)
def sync_dashboard_stored_data(active_portfolio_state, auth_data, pathname):
    if pathname != "/dashboard":
        return no_update
    if not (auth_data or {}).get("authenticated"):
        return []
    portfolio_id = _portfolio_id_from_state(active_portfolio_state)
    if not portfolio_id:
        return []
    user = get_current_user()
    if not user:
        return []
    return _serialize_transactions(user, active_portfolio_state)


@app.callback(
    Output("url", "pathname", allow_duplicate=True),
    Input("url", "pathname"),
    Input("auth-store", "data"),
    prevent_initial_call=True,
)
def guard_client_routes(pathname, auth_data):
    protected = {"/dashboard", "/predikce", "/rebalance"}
    authenticated = bool((auth_data or {}).get("authenticated"))
    if not authenticated and get_current_user():
        authenticated = True
    if pathname in protected and not authenticated:
        return "/"
    return no_update


@app.callback(
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


@app.callback(
    Output("ui-store", "data", allow_duplicate=True),
    Input("menu-toggle", "n_clicks"),
    Input("menu-close", "n_clicks"),
    State("ui-store", "data"),
    prevent_initial_call=True,
)
def toggle_menu_sidebar(menu_clicks, close_clicks, ui_data):
    if not menu_clicks and not close_clicks:
        return no_update
    current = dict(ui_data or {})
    current["menu_sidebar_open"] = not bool(current.get("menu_sidebar_open"))
    return current


@app.callback(
    Output("portfolio-list-store", "data", allow_duplicate=True),
    Output("active-portfolio-store", "data", allow_duplicate=True),
    Output("portfolio-sidebar-status", "children", allow_duplicate=True),
    Input({"type": "portfolio-select", "index": ALL}, "n_clicks"),
    Input({"type": "portfolio-delete", "index": ALL}, "n_clicks"),
    State("auth-store", "data"),
    State("language-store", "data"),
    prevent_initial_call=True,
)
def handle_portfolio_actions(_select_clicks, _delete_clicks, auth_data, language):
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
            return no_update, no_update, t(language, "index.portfolio_select_failed")
        portfolios = list_user_portfolios(user["id"])
        return portfolios, {"portfolio_id": portfolio["id"]}, t(language, "index.active_portfolio", name=portfolio["name"])

    if triggered.get("type") == "portfolio-delete":
        active, portfolios = delete_user_portfolio(user["id"], portfolio_id)
        if not active:
            return portfolios, {"portfolio_id": None}, t(language, "index.portfolio_deleted")
        return portfolios, {"portfolio_id": active["id"]}, t(language, "index.portfolio_deleted_active", name=active["name"])

    return no_update, no_update, no_update


@app.callback(
    Output("portfolio-list-store", "data", allow_duplicate=True),
    Output("active-portfolio-store", "data", allow_duplicate=True),
    Output("portfolio-create-name", "value"),
    Output("portfolio-sidebar-status", "children", allow_duplicate=True),
    Input("portfolio-create-button", "n_clicks"),
    State("portfolio-create-name", "value"),
    State("auth-store", "data"),
    State("language-store", "data"),
    prevent_initial_call=True,
)
def create_portfolio_from_sidebar(n_clicks, portfolio_name, auth_data, language):
    if not n_clicks or not (auth_data or {}).get("authenticated"):
        return no_update, no_update, no_update, no_update

    user = get_current_user()
    if not user:
        return no_update, no_update, no_update, t(language, "common.authentication_required")

    portfolio = create_user_portfolio(user["id"], portfolio_name or t(language, "sidebar.portfolio_name"))
    portfolios = list_user_portfolios(user["id"])
    status = t(language, "index.created_portfolio", name=portfolio["name"])
    return portfolios, {"portfolio_id": portfolio["id"]}, "", status


@app.callback(
    Output("portfolio-report-download", "data"),
    Output("report-status", "children"),
    Input("download-portfolio-report", "n_clicks"),
    State("active-portfolio-store", "data"),
    State("vyber-datum", "date"),
    State("language-store", "data"),
    prevent_initial_call=True,
    running=[
        (
            Output("report-progress-wrapper", "style"),
            {"display": "block"},
            {"display": "none"},
        ),
    ],
)
def export_portfolio_report(n_clicks, active_portfolio_data, selected_date, language):
    if not n_clicks:
        return no_update, no_update

    user = get_current_user()
    portfolio_id = _portfolio_id_from_state(active_portfolio_data)
    if not user:
        return no_update, t(language, "common.authentication_required")
    if not portfolio_id:
        return no_update, t(language, "common.no_active_portfolio")

    try:
        pdf_bytes, filename = generate_portfolio_report_pdf(
            user_id=user["id"],
            portfolio_id=portfolio_id,
            report_date=selected_date,
            language=language,
        )
        return (
            {
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
                "filename": filename,
                "type": "application/pdf",
                "base64": True,
            },
            t(language, "index.report_generated", filename=filename),
        )
    except Exception as exc:
        return no_update, t(language, "index.report_failed", error=str(exc))


@app.callback(
    Output("app-shell", "children"),
    Input("auth-store", "data"),
    Input("portfolio-list-store", "data"),
    Input("active-portfolio-store", "data"),
    Input("language-store", "data"),
)
def render_shell(auth_data, portfolio_list, active_portfolio, language):
    return build_app_shell(
        auth_data=auth_data or {},
        portfolios=portfolio_list or [],
        active_portfolio_id=(active_portfolio or {}).get("portfolio_id"),
        ui_data={"portfolio_sidebar_open": False, "menu_sidebar_open": False},
        language=language or "cs",
    )


@app.callback(
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


@app.callback(
    Output("mobile-menu-sidebar", "style"),
    Input("ui-store", "data"),
    Input("auth-store", "data"),
    prevent_initial_call=False,
)
def sync_mobile_menu_ui(ui_data, auth_data):
    authenticated = bool((auth_data or {}).get("authenticated"))
    menu_open = bool((ui_data or {}).get("menu_sidebar_open"))
    return {
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
        "transform": "translateX(0)" if (menu_open and authenticated) else "translateX(-100%)",
        "opacity": "1" if (menu_open and authenticated) else "0.96",
        "pointerEvents": "auto" if (menu_open and authenticated) else "none",
        "zIndex": "1250",
        "boxSizing": "border-box",
    }


if __name__ == "__main__":
    app.run(debug=True)
